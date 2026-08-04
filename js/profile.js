// profile.js - Profile page logic

// Import the auth object
import { auth } from "./auth.js"

document.addEventListener("DOMContentLoaded", async () => {
  // Get references to UI elements
  const profileLoading = document.getElementById("profile-loading")
  const profileError = document.getElementById("profile-error")
  const profileData = document.getElementById("profile-data")
  const profileName = document.getElementById("profile-name")
  const profileEmail = document.getElementById("profile-email")
  const profilePicture = document.getElementById("profile-picture")
  const profileDetailsTable = document.getElementById("profile-details-table")
  const logoutButton = document.getElementById("logout-button")

  // Check if user is authenticated
  const isAuthenticated = await auth.isAuthenticated()

  if (!isAuthenticated) {
    // User is not authenticated, redirect to login
    profileLoading.classList.add("hidden")
    profileError.textContent = "You need to be logged in to view this page. Redirecting to login..."
    profileError.classList.remove("hidden")

    setTimeout(() => {
      window.location.href = "index.html"
    }, 2000)

    return
  }

  try {
    // Get user data
    const user = await auth.getUser()

    if (!user) {
      throw new Error("Failed to load user data")
    }

    // Display user profile
    profileName.textContent = user.profile.name || "No name provided"
    profileEmail.textContent = user.profile.email || "No email provided"

    // Set profile picture if available
    if (user.profile.picture) {
      profilePicture.src = user.profile.picture
    }

    // Populate profile details table
    const profileDetails = [
      { label: "User ID", value: user.profile.sub },
      { label: "Name", value: user.profile.name },
      { label: "Email", value: user.profile.email },
      { label: "Email Verified", value: user.profile.email_verified ? "Yes" : "No" },
      { label: "Token Expires", value: new Date(user.expires_at * 1000).toLocaleString() },
    ]

    // Add any additional claims from the ID token
    for (const [key, value] of Object.entries(user.profile)) {
      if (!["sub", "name", "email", "email_verified", "picture"].includes(key)) {
        profileDetails.push({ label: formatClaimName(key), value: formatClaimValue(value) })
      }
    }

    // Clear existing table rows
    profileDetailsTable.innerHTML = ""

    // Add rows to the table
    profileDetails.forEach((detail) => {
      if (detail.value) {
        const row = document.createElement("tr")

        const labelCell = document.createElement("td")
        labelCell.className = "label"
        labelCell.textContent = detail.label

        const valueCell = document.createElement("td")
        valueCell.className = "value"
        valueCell.textContent = detail.value

        row.appendChild(labelCell)
        row.appendChild(valueCell)
        profileDetailsTable.appendChild(row)
      }
    })

    // Set up logout button
    logoutButton.onclick = () => {
      auth.logout()
    }

    // Show profile data
    profileLoading.classList.add("hidden")
    profileData.classList.remove("hidden")
  } catch (error) {
    console.error("Error loading profile:", error)
    profileLoading.classList.add("hidden")
    profileError.textContent = "Failed to load profile data: " + error.message
    profileError.classList.remove("hidden")
  }
})

// Helper function to format claim names
function formatClaimName(name) {
  return name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

// Helper function to format claim values
function formatClaimValue(value) {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No"
  }

  if (value instanceof Array) {
    return value.join(", ")
  }

  if (value instanceof Object) {
    return JSON.stringify(value)
  }

  return String(value)
}

