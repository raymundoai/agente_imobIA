import type { Property } from "../api/types";

const LOCAL_PROPERTIES_KEY = "imobos.local.properties";

export function getLocalProperties(): Property[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_PROPERTIES_KEY);
    return raw ? (JSON.parse(raw) as Property[]) : [];
  } catch {
    return [];
  }
}

export function addLocalProperty(property: Property) {
  const current = getLocalProperties();
  window.localStorage.setItem(LOCAL_PROPERTIES_KEY, JSON.stringify([property, ...current]));
}
