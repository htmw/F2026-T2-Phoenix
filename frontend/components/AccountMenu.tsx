"use client";

import { useEffect, useRef, useState } from "react";

import { loginWithGoogle, logoutSession, type SignedInUser } from "@/lib/api";

type GoogleCredential = { credential: string };

type GoogleAccounts = {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: GoogleCredential) => void;
      }) => void;
      renderButton: (parent: HTMLElement, options: { theme: string; size: string }) => void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleAccounts;
  }
}

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

export function AccountMenu() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!CLIENT_ID || !buttonRef.current) {
      return;
    }
    const parent = buttonRef.current;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: (response) => {
          void loginWithGoogle(response.credential)
            .then(setUser)
            .catch((cause: unknown) => {
              setError(cause instanceof Error ? cause.message : "Google sign-in failed");
            });
        },
      });
      window.google?.accounts.id.renderButton(parent, { theme: "outline", size: "large" });
    };
    document.body.appendChild(script);
    return () => {
      script.remove();
    };
  }, []);

  return (
    <div className="field" style={{ marginTop: 16 }}>
      <span>Google account</span>
      {user ? (
        <p className="meta">
          Signed in as {user.display_name || user.email}
          <button
            type="button"
            className="px-btn ghost"
            style={{ marginLeft: 8 }}
            onClick={() => {
              void logoutSession().then(() => setUser(null));
            }}
          >
            Log out
          </button>
        </p>
      ) : (
        <div ref={buttonRef} />
      )}
      {!CLIENT_ID && (
        <p className="muted">
          Set NEXT_PUBLIC_GOOGLE_CLIENT_ID and GOOGLE_CLIENT_ID, then AUTH_MODE=google, to
          replace the operator id with a verified Google session.
        </p>
      )}
      {error && <p className="muted">{error}</p>}
    </div>
  );
}
