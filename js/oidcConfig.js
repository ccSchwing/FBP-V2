// oidcConfig.js - centralized OIDC settings for browser auth flows

const appBaseUrl = "https://my-fbp.com";

export const oidcConfig = {
  authority: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_KSCUrIP04",
  cognitoDomain: "https://fbp-user-pool.auth.us-east-1.amazoncognito.com",
  clientId: "5oqpn67fegod7ibdthr3el78jr",
  responseType: "code",
  scope: "openid email phone",
  redirectPath: "/callback.html",
  postLogoutRedirectPath: "/index.html",
};

function toAbsoluteUrl(path) {
  return new URL(path, appBaseUrl).toString();
}

export function getRedirectUri() {
  return toAbsoluteUrl(oidcConfig.redirectPath);
}

export function getPostLogoutRedirectUri() {
  return toAbsoluteUrl(oidcConfig.postLogoutRedirectPath);
}

export function getAuthorizeUrl() {
  const params = new URLSearchParams({
    client_id: oidcConfig.clientId,
    response_type: oidcConfig.responseType,
    scope: oidcConfig.scope,
    redirect_uri: getRedirectUri(),
  });

  return `${oidcConfig.cognitoDomain}/oauth2/authorize?${params.toString()}`;
}

export function getLogoutUrl(logoutUri = getPostLogoutRedirectUri()) {
  const params = new URLSearchParams({
    client_id: oidcConfig.clientId,
    logout_uri: logoutUri,
  });

  return `${oidcConfig.cognitoDomain}/logout?${params.toString()}`;
}
