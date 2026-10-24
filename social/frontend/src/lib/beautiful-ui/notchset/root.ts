export const NOTCHSET_ROOT = {
  "data-notchset": "",
  "data-sound": "none",
  "data-sound-voice": "analogue",
} as const;

/** On every interactive element: it plays its own cues, so the page's click layer adds no tap. */
export const OWN_SOUND = { "data-sound": "none" } as const;
