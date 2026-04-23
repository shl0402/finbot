// frontend/src/lib/logger.ts
// Centralized logging for the FinBot frontend.
// All logs are prefixed with [FinBot FE].
// Errors are also POST'd to /api/log for server-side persistence.

const PREFIX = "[FinBot FE]";

function format(...args: unknown[]): string {
  return args
    .map((a) => (typeof a === "object" ? JSON.stringify(a) : String(a)))
    .join(" ");
}

function postToServer(level: string, message: string, stack?: string) {
  const postUrl = "/api/log";
  logger.debug("postToServer — level=%s url=%s message=%s", level, postUrl, message.slice(0, 100));
  fetch(postUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level,
      message,
      stack,
      url: window.location.href,
      userAgent: navigator.userAgent,
    }),
  }).catch(() => {
    // swallow — never let logging itself break the app
  });
}

export const logger = {
  debug(...args: unknown[]) {
    console.debug(PREFIX, format(...args));
  },

  info(...args: unknown[]) {
    console.info(PREFIX, format(...args));
  },

  warn(...args: unknown[]) {
    const msg = format(...args);
    console.warn(PREFIX, msg);
    postToServer("warn", msg);
  },

  error(...args: unknown[]) {
    const msg = format(...args);
    // Extract stack from Error objects in args
    const stack =
      args.find((a) => a instanceof Error) instanceof Error
        ? (args.find((a) => a instanceof Error) as Error).stack
        : undefined;
    console.error(PREFIX, msg, stack ?? "");
    postToServer("error", msg, stack);
  },
};
