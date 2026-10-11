import { getApp, getApps, initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
  browserLocalPersistence,
  getAuth,
  getRedirectResult,
  GoogleAuthProvider,
  setPersistence,
  signInWithPopup,
  signInWithRedirect,
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const button = document.getElementById("google-sign-in");
const message = document.getElementById("google-sign-in-message");
const label = document.getElementById("google-sign-in-label");
const redirectButton = document.getElementById("google-redirect-sign-in");
const configNode = document.getElementById("firebase-web-config");

if (button && message && label && redirectButton && configNode) {
  const config = JSON.parse(configNode.textContent || "{}");
  const requiredConfig = [
    "apiKey",
    "authDomain",
    "projectId",
    "appId",
  ];

  const showMessage = (text) => {
    message.textContent = text;
  };

  const errorMessage = (error) => {
    switch (error?.code) {
      case "auth/unauthorized-domain":
        return `This domain (${window.location.hostname}) is not authorized in Firebase Authentication.`;
      case "auth/operation-not-allowed":
        return "Google sign-in is not enabled for this Firebase project.";
      case "auth/invalid-api-key":
        return "Firebase configuration is invalid. Ask the site administrator to verify the Firebase web settings in Render.";
      case "auth/network-request-failed":
        return "Could not reach Firebase. Check your network connection and try again.";
      case "auth/popup-closed-by-user":
      case "auth/cancelled-popup-request":
        return "Google sign-in was cancelled or the popup closed before completion. You can try again or continue with full-page sign-in.";
      case "auth/popup-blocked":
        return "The sign-in popup was blocked. Use full-page sign-in instead.";
      case "auth/unauthorized-continue-uri":
        return "This sign-in redirect is not authorized. Ask the site administrator to check the Firebase authorized domains.";
      case "auth/account-exists-with-different-credential":
        return "An account already exists with this email using a different sign-in method. Sign in with that method first.";
      default:
        return "Google sign-in could not be completed. Please try again.";
    }
  };

  const setBusy = (busy) => {
    button.disabled = busy;
    redirectButton.disabled = busy;
    label.textContent = busy ? "Connecting to Google…" : "Continue with Google";
    button.setAttribute("aria-busy", String(busy));
    redirectButton.setAttribute("aria-busy", String(busy));
  };

  const showRedirectOption = (show) => {
    redirectButton.hidden = !show;
  };

  const completeDjangoSession = async (user) => {
    const form = document.querySelector("#login-form");
    const csrfToken = form?.querySelector('[name="csrfmiddlewaretoken"]')?.value;
    const next = form?.querySelector('[name="next"]')?.value || "";
    if (!csrfToken) {
      throw new Error("Could not read the sign-in security token. Reload the page and try again.");
    }

    const body = new URLSearchParams({
      id_token: await user.getIdToken(),
      csrfmiddlewaretoken: csrfToken,
      next,
    });
    const response = await fetch(button.dataset.sessionUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-CSRFToken": csrfToken,
        Accept: "application/json",
      },
      body,
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw new Error("The sign-in service returned an unreadable response. Please try again.");
    }
    if (!response.ok) {
      throw new Error(result.error || "Google sign-in could not be verified.");
    }
    window.location.assign(result.redirect_url);
  };

  const finishCredential = async (user) => {
    setBusy(true);
    showMessage("");
    try {
      await completeDjangoSession(user);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : errorMessage(error));
      setBusy(false);
    }
  };

  if (requiredConfig.some((key) => !config[key])) {
    button.disabled = true;
    showMessage("Google sign-in is not configured. Ask the site administrator to add Firebase web settings.");
  } else {
    let auth;
    try {
      const appName = "mybookshow-web";
      const app = getApps().some((item) => item.name === appName)
        ? getApp(appName)
        : initializeApp(config, appName);
      auth = getAuth(app);
    } catch (error) {
      button.disabled = true;
      showMessage(errorMessage(error));
    }

    if (auth) {
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });

      getRedirectResult(auth)
        .then((result) => {
          if (result) {
            return finishCredential(result.user);
          }
          return undefined;
        })
        .catch((error) => {
          showMessage(errorMessage(error));
          showRedirectOption(true);
          setBusy(false);
        });

      button.addEventListener("click", async () => {
        setBusy(true);
        showMessage("");
        showRedirectOption(false);
        try {
          await setPersistence(auth, browserLocalPersistence);
          const result = await signInWithPopup(auth, provider);
          await completeDjangoSession(result.user);
        } catch (error) {
          showMessage(
            error instanceof Error && !error.code
              ? error.message
              : errorMessage(error)
          );
          showRedirectOption(
            error?.code === "auth/popup-blocked" ||
              error?.code === "auth/popup-closed-by-user" ||
              error?.code === "auth/cancelled-popup-request" ||
              error?.code === "auth/operation-not-supported-in-this-environment"
          );
          setBusy(false);
        }
      });

      redirectButton.addEventListener("click", async () => {
        setBusy(true);
        showMessage("");
        try {
          await setPersistence(auth, browserLocalPersistence);
          await signInWithRedirect(auth, provider);
        } catch (error) {
          showMessage(
            error instanceof Error && !error.code
              ? error.message
              : errorMessage(error)
          );
          setBusy(false);
        }
      });
    }
  }
}
