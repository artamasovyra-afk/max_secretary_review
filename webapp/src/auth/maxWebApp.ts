type MaxWebAppContainer = {
  initData?: unknown;
};

type MaxWebAppWindow = Window & {
  WebApp?: MaxWebAppContainer;
  MAX?: {
    WebApp?: MaxWebAppContainer;
  };
  max?: {
    WebApp?: MaxWebAppContainer;
  };
  MiniApp?: MaxWebAppContainer;
};

export function getMaxInitData(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const maxWindow = window as MaxWebAppWindow;
  return (
    safeInitData(maxWindow.WebApp?.initData) ??
    safeInitData(maxWindow.MAX?.WebApp?.initData) ??
    safeInitData(maxWindow.max?.WebApp?.initData) ??
    safeInitData(maxWindow.MiniApp?.initData) ??
    getInitDataFromUrl()
  );
}

function safeInitData(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

function getInitDataFromUrl(): string | null {
  const hashInitData = getUrlParam(window.location.hash, "WebAppData");
  if (hashInitData) {
    return hashInitData;
  }
  return getUrlParam(window.location.search, "WebAppData");
}

function getUrlParam(source: string, key: string): string | null {
  const params = new URLSearchParams(source.replace(/^[?#]/, ""));
  return safeInitData(params.get(key));
}
