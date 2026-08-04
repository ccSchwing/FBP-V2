import { auth } from "/js/auth.js"

const statusList = document.getElementById("status-list")
const runButton = document.getElementById("run-health-check")
const hostedLogoutButton = document.getElementById("run-hosted-logout-check")
const resetButton = document.getElementById("reset-health-check")
const FLOW_KEY = "authHealthFlow"

function addStatus(message, kind = "info") {
  const li = document.createElement("li")
  li.textContent = message
  li.className = kind
  statusList.appendChild(li)
}

function setFlow(value) {
  if (!value) {
    sessionStorage.removeItem(FLOW_KEY)
    return
  }
  sessionStorage.setItem(FLOW_KEY, value)
}

async function runFlow() {
  const stage = sessionStorage.getItem(FLOW_KEY)
  const url = new URL(window.location.href)
  const callbackStage = url.searchParams.get("stage")

  if (stage === "pending-hosted-logout" && callbackStage === "post-logout") {
    addStatus("Hosted logout return detected. Verifying session is cleared...", "info")
    const authenticated = await auth.isAuthenticated()
    if (authenticated) {
      addStatus("Hosted logout check failed: user is still authenticated.", "error")
      return
    }

    addStatus("Hosted logout check passed: user is signed out after Cognito redirect.", "success")
    setFlow(null)
    url.searchParams.delete("stage")
    window.history.replaceState({}, "", url.toString())
    return
  }

  if (stage === "pending-callback-hosted-logout" && callbackStage === "callback") {
    addStatus("Callback stage reached. Starting hosted logout redirect...", "info")
    setFlow("pending-hosted-logout")
    await auth.logoutTo("https://my-fbp.com/auth-health.html?stage=post-logout")
    return
  }

  if (stage === "pending-callback" || callbackStage === "callback") {
    addStatus("Callback stage reached. Validating authenticated session...", "info")
    const authenticated = await auth.isAuthenticated()
    if (!authenticated) {
      addStatus("Auth check failed: no active session after callback.", "error")
      return
    }

    const user = await auth.getUser()
    if (!user || !user.access_token) {
      addStatus("Token check failed: access token is missing.", "error")
      return
    }

    addStatus("Token check passed.", "success")
    addStatus("Clearing local session to verify logout behavior...", "info")
    await auth.clearLocalSession()

    const postLogoutAuthenticated = await auth.isAuthenticated()
    if (postLogoutAuthenticated) {
      addStatus("Local logout check failed: session still present.", "error")
      return
    }

    addStatus("Local logout check passed.", "success")
    addStatus("Health check complete: login, callback, token, and local logout verified.", "success")
    setFlow(null)
    url.searchParams.delete("stage")
    window.history.replaceState({}, "", url.toString())
    return
  }

  addStatus("Starting login redirect...", "info")
  setFlow("pending-callback")
  await auth.fbplogin()
}

async function runHostedLogoutCheck() {
  const url = new URL(window.location.href)
  const callbackStage = url.searchParams.get("stage")
  const stage = sessionStorage.getItem(FLOW_KEY)

  if (stage === "pending-hosted-logout" && callbackStage === "post-logout") {
    await runFlow()
    return
  }

  const authenticated = await auth.isAuthenticated()
  if (!authenticated) {
    addStatus("User is not signed in. Starting login first for hosted logout test...", "info")
    setFlow("pending-callback-hosted-logout")
    await auth.fbplogin()
    return
  }

  addStatus("Starting hosted logout redirect via Cognito...", "info")
  setFlow("pending-hosted-logout")
  await auth.logoutTo("https://my-fbp.com/auth-health.html?stage=post-logout")
}

runButton.addEventListener("click", () => {
  statusList.innerHTML = ""
  runFlow().catch((error) => {
    addStatus(`Health check error: ${error.message}`, "error")
    setFlow(null)
  })
})

hostedLogoutButton.addEventListener("click", () => {
  statusList.innerHTML = ""
  runHostedLogoutCheck().catch((error) => {
    addStatus(`Hosted logout check error: ${error.message}`, "error")
    setFlow(null)
  })
})

resetButton.addEventListener("click", () => {
  setFlow(null)
  statusList.innerHTML = ""
  addStatus("Health-check state cleared.", "info")
})

addStatus("Ready. Click Run Health Check.", "info")
const urlStage = new URL(window.location.href).searchParams.get("stage")
if (urlStage === "callback" || urlStage === "post-logout") {
  runFlow().catch((error) => {
    addStatus(`Health check error: ${error.message}`, "error")
    setFlow(null)
  })
}
