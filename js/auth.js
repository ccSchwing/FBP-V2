// auth.js - OIDC Authentication Service

// Import the debug utilities
import { debugLog, initializeDebugging } from "./debug.js";
import {
  oidcConfig,
  getAuthorizeUrl,
  getLogoutUrl,
  getPostLogoutRedirectUri,
  getRedirectUri,
} from "./oidcConfig.js";

// Configure OIDC client
const authConfig = {
  authority: oidcConfig.authority,
  client_id: oidcConfig.clientId,
  redirect_uri: getRedirectUri(),
  silent_redirect_uri: `${window.location.origin}/silent.html`,
  post_logout_redirect_uri: getPostLogoutRedirectUri(),
  response_type: oidcConfig.responseType,
  scope: oidcConfig.scope,
  automaticSilentRenew: true,
  silentRequestTimeoutInSeconds: 10,
}


// Create the UserManager using the global Oidc object from the CDN script
const userManager = new oidc.UserManager(authConfig)

// Initialize debugging
const debug = initializeDebugging(userManager)

// Log OIDC events for debugging
userManager.events.addUserLoaded((user) => {
  console.log("[User Loaded] Token refreshed successfully", user)
  updateLoginStatus()
})

userManager.events.addAccessTokenExpiring(() => {
  console.log("[Access Token Expiring] Attempting silent refresh...")
})

userManager.events.addAccessTokenExpired(() => {
  console.log("[Access Token Expired] Token has expired")
})

userManager.events.addSilentRenewError((error) => {
  console.error("[Silent Renew Error]", error)
  console.error("Error details:", {
    message: error.message,
    error: error.error,
    error_description: error.error_description
  })
})

userManager.events.addUserSignedOut(() => {
  console.log("User signed out")
  userManager.removeUser()
  updateLoginStatus()
})

// Authentication functions
export const auth = {
  // Login function
  login: async () => {
    // Keep this alias for pages that still call auth.login()
    return auth.fbplogin()
  },
  fbplogin: async () => {
    try {
      debugLog("auth", "Starting login redirect")
      await userManager.signinRedirect()
    } catch (error) {
      debugLog("error", "Login error:", error)
      console.error("Login error:", error)
      return { success: false, error }
    }
  },
  signinRedirect: async () => {
    return auth.fbplogin()
  },

  fbploginOrig: async () => {
    debugLog("auth", "Starting fbplogin redirect")
    window.location.href = getAuthorizeUrl()
  },

  
  logout: async () => {
    // Hide page content immediately to prevent flash before redirect
    document.body.style.visibility = 'hidden';

    // Clear local session first
    userManager.removeUser()

    // Then redirect to Cognito logout
    window.location.href = getLogoutUrl()
  },
  logoutTo: async (logoutRedirectUri) => {
    document.body.style.visibility = 'hidden';
    userManager.removeUser()
    window.location.href = getLogoutUrl(logoutRedirectUri)
  },
  clearLocalSession: async () => {
    await userManager.removeUser()
    updateLoginStatus()
  },
  isAdmin: async () => {
  // Check if user is admin (has highest priority)
  const user = await auth.getUser()
  if (!user) return false
  const userGroups = user.profile['cognito:groups'] || [];
  const isAdmin = userGroups.includes('FBP-Admin');

  if (isAdmin) {
    // Enhanced admin functionality
    return true
  } else if (userGroups.includes('FBP-Users')) {
    // Regular user functionality
    return false
  }
  return false
  },
  // Handle the callback from the identity provider
  handleCallback: async () => {
    try {
      debugLog("auth", "Processing authentication callback")
      const user = await userManager.signinRedirectCallback()
      debugLog("token", "Authentication successful", user)
      return { success: true, user }
    } catch (error) {
      debugLog("error", "Callback error:", error)
      console.error("Callback error:", error)
      return { success: false, error }
    }
  },

  // Get the current user
  getUser: async () => {
    try {
      const user = await userManager.getUser()
      return user
    } catch (error) {
      console.error("Get user error:", error)
      return null
    }
  },

  // Check if the user is authenticated
  isAuthenticated: async () => {
    const user = await auth.getUser()
    return !!user && !user.expired
  },

  // Ensure the user is authenticated, otherwise trigger login redirect.
  ensureAuthenticated: async () => {
    const authenticated = await auth.isAuthenticated()
    if (!authenticated) {
      await auth.fbplogin()
      return false
    }
    return true
  },

  // Renew the token silently
  renewToken: async () => {
    try {
      const user = await userManager.signinSilent()
      return { success: true, user }
    } catch (error) {
      console.error("Token renewal error:", error)
      return { success: false, error }
    }
  },
}

// Update login status in the UI
async function updateLoginStatus() {
  const isAuthenticated = await auth.isAuthenticated()
  const loginStatusElement = document.getElementById("login-status")

  if (loginStatusElement) {
    if (isAuthenticated) {
      const user = await auth.getUser()
      loginStatusElement.textContent = `Logout (${user.profile.name || user.profile.email || "User"})`
      loginStatusElement.onclick = (e) => {
        e.preventDefault()
        auth.logout()
      }
    } else {
      loginStatusElement.textContent = "Login"
      loginStatusElement.onclick = (e) => {
        e.preventDefault()
        auth.fbplogin()
      }
    }
  }
}

// Initialize auth status when the page loads
document.addEventListener("DOMContentLoaded", () => {
  updateLoginStatus()
})

