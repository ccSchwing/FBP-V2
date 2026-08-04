import { getServiceUrl } from "/js-lib/urlConfig.js";

const DEFAULT_MESSAGES = {
  "not-set": "Add a mobile number to enable SMS notifications. Digits only.  Formatting is automatic.",
  pending: "Verify this number to enable SMS notifications.",
  verified: "This mobile number is verified.",
};

function parseResponseBody(responseData) {
  if (!responseData || typeof responseData !== "object") {
    return {};
  }

  if (typeof responseData.body === "string") {
    try {
      return JSON.parse(responseData.body);
    } catch {
      return {};
    }
  }

  return responseData.body || responseData;
}

function getStateLabel(stateKey) {
  if (stateKey === "verified") return "Verified";
  if (stateKey === "pending") return "Pending";
  return "Not Set";
}

function deriveState(profileBody) {
  const mobileDigits = normalizePhoneNumber(profileBody?.mobile_number || "");
  const status = String(profileBody?.sms_verification_status || "")
    .trim()
    .toUpperCase();

  if (status === "VERIFIED" && mobileDigits) {
    return { stateKey: "verified", digits: mobileDigits };
  }

  if (status === "PENDING" && mobileDigits) {
    return { stateKey: "pending", digits: mobileDigits };
  }

  if (mobileDigits) {
    return { stateKey: "pending", digits: mobileDigits };
  }

  return { stateKey: "not-set", digits: "" };
}

export function normalizePhoneNumber(value = "") {
  return String(value || "").replace(/\D/g, "").slice(0, 10);
}

export function formatPhoneNumber(value = "") {
  const digits = normalizePhoneNumber(value);

  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  }
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

async function hashString(inputString) {
  const encoder = new TextEncoder();
  const data = encoder.encode(inputString);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function initPhoneVerification({ resolveUserEmail } = {}) {
  const elementIds = {
    mobileInput: "MobileNumber",
    codeInput: "MobileNumberVerification",
    sendButton: "sendSMSVerificationCodeBtn",
    verifyButton: "verifySMSMobileNumberBtn",
    stateBadge: "mobileVerificationState",
    stateMessage: "mobileVerificationMessage",
    smsReminder: "smsReminder",
    smsPickSheet: "smsPickSheet",
    smsGridSheet: "smsGridSheet",
  };

  let verifiedDigits = "";
  let listenersBound = false;

  function getElements() {
    return {
      mobileInput: document.getElementById(elementIds.mobileInput),
      codeInput: document.getElementById(elementIds.codeInput),
      sendButton: document.getElementById(elementIds.sendButton),
      verifyButton: document.getElementById(elementIds.verifyButton),
      stateBadge: document.getElementById(elementIds.stateBadge),
      stateMessage: document.getElementById(elementIds.stateMessage),
      smsOptions: [
        document.getElementById(elementIds.smsReminder),
        document.getElementById(elementIds.smsPickSheet),
        document.getElementById(elementIds.smsGridSheet),
      ].filter(Boolean),
    };
  }

  function setSmsOptionsEnabled(enabled) {
    for (const checkbox of getElements().smsOptions) {
      checkbox.disabled = !enabled;
    }
  }

  function renderState(stateKey, message = DEFAULT_MESSAGES[stateKey]) {
    const { stateBadge, stateMessage } = getElements();

    if (stateBadge) {
      stateBadge.dataset.state = stateKey;
      stateBadge.textContent = getStateLabel(stateKey);
    }

    if (stateMessage) {
      stateMessage.textContent = message;
    }

    setSmsOptionsEnabled(stateKey === "verified");
  }

  function applyProfileData(profileBody = {}) {
    const { mobileInput, codeInput } = getElements();
    const { stateKey, digits } = deriveState(profileBody);

    if (mobileInput) {
      mobileInput.value = formatPhoneNumber(digits);
    }

    if (codeInput) {
      codeInput.value = "";
    }

    verifiedDigits = stateKey === "verified" ? digits : "";
    renderState(stateKey);
  }

  function updateStateForInput(rawValue) {
    const digits = normalizePhoneNumber(rawValue);

    if (!digits) {
      verifiedDigits = "";
      renderState("not-set");
      return;
    }

    if (verifiedDigits && digits === verifiedDigits) {
      renderState("verified");
      return;
    }

    renderState("pending", "Verify this number before enabling SMS notifications.");
  }

  async function getResolvedEmail() {
    if (typeof resolveUserEmail !== "function") {
      throw new Error("resolveUserEmail is not configured for phone verification.");
    }

    const email = await resolveUserEmail();
    if (!email) {
      throw new Error("No authenticated user email found.");
    }

    return email;
  }

  async function fetchStoredVerificationHash() {
    const lambdaURL = await getServiceUrl("getSMSVerificationCode");
    const response = await fetch(lambdaURL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: await getResolvedEmail() }),
    });

    if (!response.ok) {
      throw new Error(`Failed to get SMS verification code: ${response.statusText}`);
    }

    return parseResponseBody(await response.json()).verification_code_hash;
  }

  async function updateVerificationStatus() {
    const lambdaURL = await getServiceUrl("updateSMSVerification");
    const response = await fetch(lambdaURL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: await getResolvedEmail() }),
    });

    if (!response.ok) {
      throw new Error(`Failed to update SMS verification status: ${response.statusText}`);
    }
  }

  async function sendVerificationCode() {
    const { mobileInput, sendButton, codeInput } = getElements();
    const mobileDigits = normalizePhoneNumber(mobileInput?.value || "");

    if (mobileDigits.length !== 10) {
      alert("Please enter a valid 10-digit mobile number.");
      return;
    }

    if (sendButton) {
      sendButton.disabled = true;
    }

    try {
      const lambdaURL = await getServiceUrl("storeSMSVerificationCode");
      const response = await fetch(lambdaURL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mobile_number: mobileDigits,
          email: await getResolvedEmail(),
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to store SMS verification code: ${response.statusText}`);
      }

      renderState("pending", "Code sent. Enter the 6-digit code to verify this number.");
      if (codeInput) {
        codeInput.focus();
      }
      alert("SMS verification code sent successfully!");
    } catch (error) {
      console.error("Error:", error);
      alert(error.message || "Failed to store SMS verification code.");
    } finally {
      if (sendButton) {
        sendButton.disabled = false;
      }
    }
  }

  async function verifyMobileNumber() {
    const { mobileInput, codeInput, verifyButton } = getElements();
    const mobileDigits = normalizePhoneNumber(mobileInput?.value || "");
    const verificationCode = String(codeInput?.value || "").trim();

    if (mobileDigits.length !== 10) {
      alert("Please enter a valid 10-digit mobile number.");
      return;
    }

    if (verificationCode.length !== 6) {
      alert("Please enter the 6-digit verification code.");
      return;
    }

    if (verifyButton) {
      verifyButton.disabled = true;
    }

    try {
      const hashedVerificationCode = await hashString(verificationCode);
      const storedVerificationCode = await fetchStoredVerificationHash();

      if (!storedVerificationCode || hashedVerificationCode !== storedVerificationCode) {
        renderState("pending", "Invalid code. Please try again.");
        alert("Invalid verification code. Please try again.");
        return;
      }

      await updateVerificationStatus();
      verifiedDigits = mobileDigits;
      renderState("verified");
      if (codeInput) {
        codeInput.value = "";
      }
      alert("Mobile number verified successfully!");
    } catch (error) {
      console.error("Error:", error);
      alert(error.message || "Failed to verify mobile number.");
    } finally {
      if (verifyButton) {
        verifyButton.disabled = false;
      }
    }
  }

  function bindListeners() {
    if (listenersBound) {
      return;
    }

    const { mobileInput, sendButton, verifyButton } = getElements();
    let boundAny = false;

    if (mobileInput) {
      mobileInput.addEventListener("input", (event) => {
        event.target.value = formatPhoneNumber(event.target.value);
        updateStateForInput(event.target.value);
      });
      boundAny = true;
    } else {
      console.warn("Phone verification: mobile input not found.");
    }

    if (sendButton) {
      sendButton.addEventListener("click", (event) => {
        event.preventDefault();
        void sendVerificationCode();
      });
      boundAny = true;
    } else {
      console.warn("Phone verification: send verification button not found.");
    }

    if (verifyButton) {
      verifyButton.addEventListener("click", (event) => {
        event.preventDefault();
        void verifyMobileNumber();
      });
      boundAny = true;
    } else {
      console.warn("Phone verification: verify button not found.");
    }

    listenersBound = boundAny;
    if (listenersBound) {
      console.info("Phone verification listeners bound.");
    }
  }

  function applyCurrentProfile() {
    if (!window.userProfileData) {
      renderState("not-set");
      return;
    }

    const profileBody = parseResponseBody(window.userProfileData);
    applyProfileData(profileBody);
  }

  function init() {
    bindListeners();
    applyCurrentProfile();
    window.addEventListener("userProfileDataLoaded", (event) => {
      applyProfileData(parseResponseBody(event.detail));
    });
  }

  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  return {
    applyProfileData,
    getNormalizedMobileNumber() {
      return normalizePhoneNumber(getElements().mobileInput?.value || "");
    },
  };
}