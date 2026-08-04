let urlMapPromise;

async function loadUrlMap() {
  const response = await fetch('/resources/fbp-urls.txt', {
    cache: 'no-store'
  });

  if (!response.ok) {
    throw new Error(`Failed to load URL config: HTTP ${response.status}`);
  }

  const text = await response.text();
  const map = new Map();

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }

    const separatorIndex = line.indexOf(':');
    if (separatorIndex <= 0) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    const url = line.slice(separatorIndex + 1).trim();

    if (key && url) {
      map.set(key, url);
    }
  }

  return map;
}

export async function getServiceUrl(key) {
  if (!urlMapPromise) {
    urlMapPromise = loadUrlMap();
  }

  const map = await urlMapPromise;
  const url = map.get(key);

  if (!url) {
    throw new Error(`URL key not found: ${key}`);
  }

  return url;
}

export function clearServiceUrlCache() {
  urlMapPromise = undefined;
}
