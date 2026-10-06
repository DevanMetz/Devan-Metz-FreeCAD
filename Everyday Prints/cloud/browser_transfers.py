"""Inject a delayed browser reader that deliberately ignores cancellation.

The real response has already completed. This exercises late data and caller
state guards independently of the browser's normal fetch cancellation.
"""
DEFERRED_BODY = """window.deferFileBody = (response, bytes, wait) => {
  let sent = false;
  Object.defineProperty(response, 'body', { value: { getReader: () => ({
    read: async () => {
      if (sent) return { done: true };
      sent = true;
      await wait();
      return { done: false, value: new Uint8Array(bytes) };
    },
    cancel: async () => {},
    releaseLock: () => {}
  }) } });
};"""
