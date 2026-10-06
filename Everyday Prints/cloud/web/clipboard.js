export function clipboardQueue(write) {
  let active = false, queued;
  async function run(job) {
    active = true;
    try { await write(job.text); job.resolve(true); }
    catch (error) { job.reject(error); }
    finally {
      active = false;
      const next = queued;
      queued = null;
      if (next) void run(next);
    }
  }
  return text => new Promise((resolve, reject) => {
    const job = { text, resolve, reject };
    if (active) {
      queued?.resolve(false);
      queued = job;
    } else void run(job);
  });
}
