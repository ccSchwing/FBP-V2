// callback.js - Handle the authentication callback

// Import the auth object
import { auth } from "./auth.js"

document.addEventListener("DOMContentLoaded", async () => {
  try {
    // Process the authentication response
    const result = await auth.handleCallback()

    if (result.success) {
      const healthFlowStage = sessionStorage.getItem("authHealthFlow")
      if (healthFlowStage && healthFlowStage.startsWith("pending-callback")) {
        window.location.href = "/auth-health.html?stage=callback"
      } else {
        window.location.href = "fbp-home.html"
      }
    } else {
      // Display error
      document.querySelector(".card-content").innerHTML = `
        <div class="error">
          <p>There was an error processing your login:</p>
          <p>${result.error.message}</p>
          <a href="index.html" class="btn btn-primary">Return to Home</a>
        </div>
      `
    }
  } catch (error) {
    console.error("Callback processing error:", error)

    // Display error
    document.querySelector(".card-content").innerHTML = `
      <div class="error">
        <p>There was an unexpected error processing your login:</p>
        <p>${error.message}</p>
        <a href="index.html" class="btn btn-primary">Return to Home</a>
      </div>
    `
  }
})

