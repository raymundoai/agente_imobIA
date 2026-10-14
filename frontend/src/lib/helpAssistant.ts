export const HELP_OPEN_EVENT = "immobia:open-help";
export const HELP_DOCKED_EVENT = "immobia:help-docked";
export const HELP_DOCKED_KEY = "immobia.assistant.docked";

export function isHelpDocked() {
  try {
    return window.localStorage.getItem(HELP_DOCKED_KEY) === "true";
  } catch {
    return false;
  }
}

export function openHelp() {
  window.dispatchEvent(new Event(HELP_OPEN_EVENT));
}
