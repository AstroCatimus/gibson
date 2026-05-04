/**
 * Gibson — Debug Logger
 * Stores recent log entries in memory and prints to console.
 * View logs in Settings → Debug Logs.
 */

const MAX_ENTRIES = 150;
const entries = [];
let listeners = [];

function addEntry(level, message, data) {
  const entry = {
    id:        Date.now() + Math.random(),
    level,     // 'info' | 'warn' | 'error' | 'debug'
    message,
    data:      data !== undefined ? JSON.stringify(data, null, 2) : null,
    timestamp: new Date().toISOString(),
  };

  entries.unshift(entry); // newest first
  if (entries.length > MAX_ENTRIES) entries.splice(MAX_ENTRIES);

  // Notify any subscribed log viewers
  listeners.forEach(fn => fn([...entries]));

  // Also print to Metro console
  const tag = `[Gibson ${level.toUpperCase()}]`;
  if (level === 'error') console.error(tag, message, data ?? '');
  else if (level === 'warn') console.warn(tag, message, data ?? '');
  else console.log(tag, message, data ?? '');
}

export const logger = {
  info:  (msg, data) => addEntry('info',  msg, data),
  warn:  (msg, data) => addEntry('warn',  msg, data),
  error: (msg, data) => addEntry('error', msg, data),
  debug: (msg, data) => addEntry('debug', msg, data),

  getLogs: () => [...entries],

  clear: () => {
    entries.splice(0);
    listeners.forEach(fn => fn([]));
  },

  /** Subscribe to live log updates. Returns unsubscribe fn. */
  subscribe: (fn) => {
    listeners.push(fn);
    fn([...entries]); // immediate snapshot
    return () => { listeners = listeners.filter(l => l !== fn); };
  },
};
