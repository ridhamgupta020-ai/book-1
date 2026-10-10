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
const configNode = document.getElementById("firebase-web-config");

if (button && message && label && configNode) {
  const config = JSON.parse(configNode.textContent || "{}");
  const requiredConfig = [
    "apiKey",
    "authDomain",
    "projectId",
    "storageBucket",
    "messagingSenderId",
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
        return "Firebase configuration is invalid. Check the public Firebase web settings.";
      case "auth/network-request-failed":
        return "Could not reach Firebase. Check your network connection and try again.";
      case "auth/popup-closed-by-user":
        return "The Google sign-in window was closed before sign-in completed.";
      case "auth/popup-blocked":
        return "The sign-in popup was blocked. Switching to the redirect flow.";
      default:
        return "Google sign-in could not be completed. Please try again.";
    }
  };

  const setBusy = (busy) => {
    button.disabled = busy;
    label.textContent = busy ? "Connecting to Google…" : "Continue with Google";
    button.setAttribute("aria-busy", String(busy));
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

  const appName = "mybookshow-web";
  const app = getApps().some((item) => item.name === appName)
    ? getApp(appName)
    : initializeApp(config, appName);
  const auth = getAuth(app);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });

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
    getRedirectResult(auth)
      .then((result) => {
        if (result) {
          return finishCredential(result.user);
        }
        return undefined;
      })
      .catch((error) => showMessage(errorMessage(error)));

    button.addEventListener("click", async () => {
      setBusy(true);
      showMessage("");
      try {
        await setPersistence(auth, browserLocalPersistence);
        const result = await signInWithPopup(auth, provider);
        await completeDjangoSession(result.user);
      } catch (error) {
        if (
          error?.code === "auth/popup-blocked" ||
          error?.code === "auth/operation-not-supported-in-this-environment"
        ) {
          try {
            await setPersistence(auth, browserLocalPersistence);
            await signInWithRedirect(auth, provider);
            return;
          } catch (redirectError) {
            showMessage(errorMessage(redirectError));
          }
        } else if (error instanceof Error && !error.code) {
          showMessage(error.message);
        } else {
          showMessage(errorMessage(error));
        }
        setBusy(false);
      }
    });
  }
}
