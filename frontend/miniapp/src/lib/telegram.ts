/**
 * Helpers para acceder al SDK de Telegram Mini Apps via window.Telegram.WebApp.
 * Adaptamos para que sea utilizable tanto dentro de Telegram como standalone (web).
 */

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: { id: number; first_name?: string; username?: string; language_code?: string };
  };
  themeParams: Record<string, string>;
  colorScheme: "light" | "dark";
  viewportHeight: number;
  viewportStableHeight: number;
  ready: () => void;
  expand: () => void;
  close: () => void;
  HapticFeedback: {
    impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
    notificationOccurred: (type: "error" | "success" | "warning") => void;
    selectionChanged: () => void;
  };
  MainButton: {
    text: string;
    show: () => void;
    hide: () => void;
    enable: () => void;
    disable: () => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
    setText: (text: string) => void;
  };
  BackButton: {
    show: () => void;
    hide: () => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
  };
  CloudStorage: {
    setItem: (key: string, value: string, cb?: (err: any, ok: boolean) => void) => void;
    getItem: (key: string, cb: (err: any, value: string | undefined) => void) => void;
    removeItem: (key: string, cb?: (err: any, ok: boolean) => void) => void;
  };
  openLink: (url: string, options?: { try_instant_view?: boolean }) => void;
  openTelegramLink: (url: string) => void;
  showAlert: (msg: string, cb?: () => void) => void;
}

export function getTg(): TelegramWebApp | null {
  if (typeof window === "undefined") return null;
  return (window as any).Telegram?.WebApp ?? null;
}

export function inTelegram(): boolean {
  const tg = getTg();
  return !!tg && !!tg.initData;
}

export function haptic(style: "light" | "medium" | "heavy" = "medium") {
  try {
    getTg()?.HapticFeedback.impactOccurred(style);
  } catch {}
}

export function notifyHaptic(kind: "success" | "error" | "warning") {
  try {
    getTg()?.HapticFeedback.notificationOccurred(kind);
  } catch {}
}
