"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { getOperatorId, loginWithGoogle, setOperatorId } from "@/lib/api";
import { BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

export default function LoginPage() {
  const router = useRouter();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [operator, setOperator] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOperator(getOperatorId());
  }, []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !buttonRef.current) {
      return;
    }
    const parent = buttonRef.current;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          setBusy(true);
          setError(null);
          void loginWithGoogle(response.credential)
            .then(() => router.push("/office"))
            .catch((cause) => {
              setError(cause instanceof Error ? cause.message : "Google sign-in failed");
            })
            .finally(() => setBusy(false));
        },
      });
      parent.innerHTML = "";
      window.google?.accounts.id.renderButton(parent, {
        theme: "outline",
        size: "large",
      });
    };
    document.head.appendChild(script);
  }, [router]);

  const continueAsOperator = (event: FormEvent) => {
    event.preventDefault();
    const value = operator.trim() || "operator";
    setOperatorId(value);
    router.push("/office");
  };

  return (
    <main className="login-shell" data-testid="login-page">
      <section className="login-card">
        <BrandLogo size={48} variant="mark" />
        <h1>{BRAND_NAME}</h1>
        <p>{BRAND_TAGLINE}</p>

        {GOOGLE_CLIENT_ID ? (
          <>
            <div ref={buttonRef} data-testid="google-signin" />
            <p className="meta">
              Google sign-in uses a verified ID token. Configure AUTH_MODE=google on the API.
            </p>
          </>
        ) : (
          <p className="meta" data-testid="login-google-hint">
            Google client id is not configured. Use local demo identity below, or set
            NEXT_PUBLIC_GOOGLE_CLIENT_ID.
          </p>
        )}

        <form onSubmit={continueAsOperator} className="stack-gap" style={{ marginTop: 16 }}>
          <label className="field">
            <span>Local operator id</span>
            <input
              data-testid="login-operator"
              value={operator}
              disabled={busy}
              onChange={(event) => setOperator(event.target.value)}
              placeholder="operator"
            />
          </label>
          {error && (
            <p className="banner-err" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="px-btn primary" disabled={busy} data-testid="login-continue">
            Continue to workspace
          </button>
        </form>

        <p className="meta" style={{ marginTop: 16 }}>
          <Link href="/office">Skip to office</Link>
          {" · "}
          <Link href="/">Product site</Link>
        </p>
      </section>
    </main>
  );
}
