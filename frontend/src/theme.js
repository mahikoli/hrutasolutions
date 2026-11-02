// Theme and Appearance System for HRUTA OneCRM

export const THEMES = [
  {
    id: "modern",
    name: "Modern Professional",
    subtitle: "Linear & Stripe inspired",
    description: "Crisp white & slate canvas, deep navy structure, electric blue accents.",
    accent: "#2563eb",
    previewBg: "#f8fafc",
    previewCard: "#ffffff",
    previewBorder: "#e2e8f0",
  },
  {
    id: "midnight",
    name: "Midnight Pro",
    subtitle: "Dark charcoal & electric blue",
    description: "Deep obsidian workspace, luminous electric cyan & sapphire glow.",
    accent: "#38bdf8",
    previewBg: "#090d16",
    previewCard: "#111827",
    previewBorder: "#1f293d",
  },
  {
    id: "aurora",
    name: "Aurora",
    subtitle: "Lavender & violet gradient",
    description: "Soft violet undertones, luminous twilight gradients and indigo depth.",
    accent: "#7c3aed",
    previewBg: "#fdf8ff",
    previewCard: "#ffffff",
    previewBorder: "#f1e5f8",
  },
  {
    id: "emerald",
    name: "Emerald Business",
    subtitle: "Forest green & emerald",
    description: "Classic executive green, mint accents, rich enterprise prestige.",
    accent: "#059669",
    previewBg: "#f4f7f5",
    previewCard: "#ffffff",
    previewBorder: "#e4ebe6",
  },
];

export const ACCENTS = [
  { id: "default", name: "Theme Default", color: "inherit" },
  { id: "blue", name: "Electric Blue", color: "#2563eb" },
  { id: "violet", name: "Royal Violet", color: "#7c3aed" },
  { id: "emerald", name: "Emerald Mint", color: "#059669" },
  { id: "amber", name: "Sun Amber", color: "#d97706" },
  { id: "rose", name: "Crimson Rose", color: "#e11d48" },
];

export function getStoredTheme() {
  return localStorage.getItem("onecrm_theme") || "modern";
}

export function getStoredMode() {
  return localStorage.getItem("onecrm_mode") || "light";
}

export function getStoredAccent() {
  return localStorage.getItem("onecrm_accent") || "default";
}

export function applyTheme(theme = getStoredTheme(), mode = getStoredMode(), accent = getStoredAccent()) {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.setAttribute("data-mode", mode);
  root.setAttribute("data-accent", accent);

  localStorage.setItem("onecrm_theme", theme);
  localStorage.setItem("onecrm_mode", mode);
  localStorage.setItem("onecrm_accent", accent);

  if (accent !== "default") {
    const accObj = ACCENTS.find((a) => a.id === accent);
    if (accObj && accObj.color !== "inherit") {
      root.style.setProperty("--accent-custom", accObj.color);
    } else {
      root.style.removeProperty("--accent-custom");
    }
  } else {
    root.style.removeProperty("--accent-custom");
  }

  // Dispatch custom event for reactive components
  window.dispatchEvent(new CustomEvent("onecrm-theme-changed", { detail: { theme, mode, accent } }));
}

// Auto-initialize on load
if (typeof window !== "undefined") {
  applyTheme(getStoredTheme(), getStoredMode(), getStoredAccent());
}
