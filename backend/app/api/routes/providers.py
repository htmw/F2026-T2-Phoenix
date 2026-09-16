"""Provider catalogue and connection management.

Lists every supported vendor (connected or not), accepts API keys through Settings,
tests them, refreshes live model lists, and disconnects. Credentials are never echoed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.dependencies import (
    AbuseGuardDep,
    OperatorDep,
    ProviderRegistryDep,
    SessionDep,
    SettingsDep,
)
from app.domain.enums import ProviderConnectionStatus
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ModelSpec
from app.providers.openai_compatible import (
    CohereProvider,
    DeepSeekProvider,
    GeminiProvider,
    GroqProvider,
    MistralProvider,
    MoonshotProvider,
    OpenAIProvider,
    OpenRouterProvider,
    PerplexityProvider,
    QwenProvider,
    TogetherProvider,
    XAIProvider,
)
from app.schemas.api import (
    ModelView,
    ProviderActionResult,
    ProviderConnectRequest,
    ProviderStatusView,
)
from app.services import provider_connections as connections
from app.services import provider_management as management
from app.services import routing_policy as routing_policy_service

router = APIRouter(prefix="/providers", tags=["providers"])

_CATALOGUE_MODELS: dict[str, tuple] = {
    "openai": OpenAIProvider.models,
    "anthropic": AnthropicProvider.models,
    "google": GeminiProvider.models,
    "moonshot": MoonshotProvider.models,
    "groq": GroqProvider.models,
    "deepseek": DeepSeekProvider.models,
    "xai": XAIProvider.models,
    "mistral": MistralProvider.models,
    "cohere": CohereProvider.models,
    "perplexity": PerplexityProvider.models,
    "together": TogetherProvider.models,
    "qwen": QwenProvider.models,
    "openrouter": OpenRouterProvider.models,
}


def _model_view(model: ModelSpec, *, demo: bool = False, verified: bool = False) -> ModelView:
    return ModelView(
        id=model.id,
        provider=model.provider,
        traits=sorted(trait.value for trait in model.traits),
        context_tokens=model.context_tokens,
        max_output_tokens=model.max_output_tokens,
        input_cost_per_million=model.input_cost_per_million,
        output_cost_per_million=model.output_cost_per_million,
        demo=demo,
        verified=verified,
    )


async def _build_status(
    *,
    provider_id: str,
    providers: ProviderRegistryDep,
    session: SessionDep,
    settings: SettingsDep,
) -> ProviderStatusView:
    demo = provider_id == "fake"
    entry = next((item for item in management.PROVIDER_CATALOG if item.id == provider_id), None)
    label = management.provider_label(provider_id)
    auth_method = entry.auth_method if entry else "api_key"
    access_label = "Development mock" if demo else (entry.access_label if entry else "API")

    connection = None if demo else await connections.get_connection(session, provider_id)
    env_key = None if demo else management.env_key_for(settings, provider_id)
    live = providers.names and provider_id in providers.names

    if demo:
        credential_source = "demo"
        connection_status = "connected" if live else "disconnected"
        key_hint = None
        last_verified = None
        last_error = None
        discovered: list[str] = []
        configured = live
    elif connection is not None:
        credential_source = "connection"
        connection_status = connection.status
        key_hint = connection.key_hint
        last_verified = connection.last_verified_at
        last_error = connection.last_error
        discovered = list(connection.discovered_models or [])
        configured = connection.status == ProviderConnectionStatus.CONNECTED.value
    elif env_key:
        credential_source = "env"
        connection_status = "connected" if live else "unavailable"
        key_hint = connections.mask_api_key(env_key)
        last_verified = None
        last_error = None
        discovered = []
        configured = True
    else:
        credential_source = "none"
        connection_status = "disconnected"
        key_hint = None
        last_verified = None
        last_error = None
        discovered = []
        configured = False

    models: list[ModelView] = []
    if live:
        provider = providers.get(provider_id)
        verified_names = set(discovered)
        for model in provider.get_model_capabilities():
            models.append(
                _model_view(
                    model,
                    demo=demo,
                    verified=not verified_names or model.model_name in verified_names,
                )
            )
    elif configured and not demo:
        for model in _CATALOGUE_MODELS.get(provider_id, ()):
            models.append(_model_view(model, verified=False))

    return ProviderStatusView(
        name=provider_id,
        label=label,
        configured=configured,
        demo=demo,
        auth_method=auth_method,
        access_label=access_label,
        connection_status=connection_status,
        credential_source=credential_source,
        key_hint=key_hint,
        last_verified_at=last_verified,
        last_error=last_error,
        discovered_models=discovered,
        models=models,
    )


@router.get("", response_model=list[ProviderStatusView], summary="List providers")
async def list_providers(
    providers: ProviderRegistryDep,
    session: SessionDep,
    settings: SettingsDep,
    include_demo: bool = Query(
        default=True,
        description="Include the development Demo provider when it is registered.",
    ),
) -> list[ProviderStatusView]:
    views: list[ProviderStatusView] = []
    for entry in management.PROVIDER_CATALOG:
        views.append(
            await _build_status(
                provider_id=entry.id,
                providers=providers,
                session=session,
                settings=settings,
            )
        )
    if include_demo and "fake" in providers.names:
        views.append(
            await _build_status(
                provider_id="fake",
                providers=providers,
                session=session,
                settings=settings,
            )
        )
    return views


@router.get(
    "/routing-policy",
    response_model=routing_policy_service.RoutingPolicyView,
    summary="Get office provider priority and blocked models",
)
async def get_routing_policy(session: SessionDep) -> routing_policy_service.RoutingPolicyView:
    policy = await routing_policy_service.get_policy(session)
    return routing_policy_service.view_from_policy(policy)


@router.put(
    "/routing-policy",
    response_model=routing_policy_service.RoutingPolicyView,
    summary="Update office provider priority and blocked models",
)
async def put_routing_policy(
    body: routing_policy_service.RoutingPolicyUpdate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> routing_policy_service.RoutingPolicyView:
    _ = operator
    policy = await routing_policy_service.update_policy(session, body)
    await management.rebuild_app_registry(request, session, settings)
    return routing_policy_service.view_from_policy(policy)


@router.post(
    "/{provider_id}/connect",
    response_model=ProviderActionResult,
    status_code=status.HTTP_200_OK,
    summary="Connect a provider with an API key",
)
async def connect_provider(
    provider_id: str,
    body: ProviderConnectRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _providers: ProviderRegistryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> ProviderActionResult:
    _ = operator
    if provider_id == "fake" or provider_id not in {
        entry.id for entry in management.PROVIDER_CATALOG
    }:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'")

    status_value, discovered, error = await management.test_provider_key(provider_id, body.api_key)
    if status_value is not ProviderConnectionStatus.CONNECTED:
        raise HTTPException(
            status_code=400,
            detail=management.redact_error(error or "Connection failed."),
        )

    await connections.upsert_connection(
        session,
        settings,
        provider_id=provider_id,
        api_key=body.api_key,
        status=status_value,
        discovered_models=discovered,
        last_error=None,
    )
    await management.rebuild_app_registry(request, session, settings)
    live = request.app.state.provider_registry
    view = await _build_status(
        provider_id=provider_id, providers=live, session=session, settings=settings
    )
    return ProviderActionResult(
        provider=view,
        message=f"Connected. {len(discovered)} model id(s) discovered."
        if discovered
        else "Connected.",
    )


@router.post(
    "/{provider_id}/test",
    response_model=ProviderActionResult,
    summary="Test an existing provider connection",
)
async def test_provider(
    provider_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _providers: ProviderRegistryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> ProviderActionResult:
    _ = operator
    if provider_id not in {entry.id for entry in management.PROVIDER_CATALOG}:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'")

    api_key = None
    connection = await connections.get_connection(session, provider_id)
    if connection is not None:
        try:
            api_key = connections.decrypt_secret(settings, connection.encrypted_api_key)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail="Stored credential could not be decrypted."
            ) from exc
    else:
        api_key = management.env_key_for(settings, provider_id)

    if not api_key:
        raise HTTPException(status_code=400, detail="Provider is not connected.")

    status_value, discovered, error = await management.test_provider_key(provider_id, api_key)
    if connection is not None:
        await connections.mark_connection(
            session,
            provider_id,
            status=status_value,
            last_error=management.redact_error(error) if error else None,
            discovered_models=discovered,
        )
    await management.rebuild_app_registry(request, session, settings)
    live = request.app.state.provider_registry
    view = await _build_status(
        provider_id=provider_id, providers=live, session=session, settings=settings
    )
    return ProviderActionResult(
        provider=view,
        message="Connection healthy."
        if status_value is ProviderConnectionStatus.CONNECTED
        else (error or "Test failed."),
    )


@router.post(
    "/{provider_id}/refresh-models",
    response_model=ProviderActionResult,
    summary="Refresh discovered models from the provider API",
)
async def refresh_models(
    provider_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    providers: ProviderRegistryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> ProviderActionResult:
    return await test_provider(
        provider_id, request, session, settings, providers, operator, _limits
    )


@router.delete(
    "/{provider_id}/disconnect",
    response_model=ProviderActionResult,
    summary="Disconnect a Settings-managed provider credential",
)
async def disconnect_provider(
    provider_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _providers: ProviderRegistryDep,
    operator: OperatorDep,
    _limits: AbuseGuardDep,
) -> ProviderActionResult:
    _ = operator
    if provider_id not in {entry.id for entry in management.PROVIDER_CATALOG}:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'")

    deleted = await connections.delete_connection(session, provider_id)
    await management.rebuild_app_registry(request, session, settings)
    live = request.app.state.provider_registry
    view = await _build_status(
        provider_id=provider_id, providers=live, session=session, settings=settings
    )
    env_still = management.env_key_for(settings, provider_id) is not None
    message = (
        "Disconnected Settings credential. Environment key still active."
        if env_still
        else ("Disconnected." if deleted else "No Settings credential was stored.")
    )
    return ProviderActionResult(provider=view, message=message)
