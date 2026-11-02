import React, { useState, useEffect } from "react";
import { Check, Sun, Moon, Palette, Sparkles, Sliders } from "lucide-react";
import { THEMES, ACCENTS, applyTheme, getStoredTheme, getStoredMode, getStoredAccent } from "../theme";

export function QuickThemeSwitcher() {
  const [open, setOpen] = useState(false);
  const [currentTheme, setCurrentTheme] = useState(getStoredTheme());
  const [currentMode, setCurrentMode] = useState(getStoredMode());

  useEffect(() => {
    const handleThemeChange = (e) => {
      setCurrentTheme(e.detail.theme);
      setCurrentMode(e.detail.mode);
    };
    window.addEventListener("onecrm-theme-changed", handleThemeChange);
    return () => window.removeEventListener("onecrm-theme-changed", handleThemeChange);
  }, []);

  const handleSelectTheme = (themeId) => {
    applyTheme(themeId, currentMode);
  };

  const handleToggleMode = () => {
    const nextMode = currentMode === "dark" ? "light" : "dark";
    applyTheme(currentTheme, nextMode);
  };

  return (
    <div className="quick-theme-container">
      <button
        className="icon-button theme-toggle-btn"
        title="Change theme & appearance"
        onClick={() => setOpen(!open)}
        aria-label="Theme switcher"
      >
        <Palette size={17} />
      </button>

      {open && (
        <>
          <div className="dropdown-scrim" onClick={() => setOpen(false)} />
          <div className="quick-theme-dropdown">
            <div className="dropdown-header">
              <span>Theme & Appearance</span>
              <button
                className="mode-toggle-chip"
                onClick={handleToggleMode}
                title={`Switch to ${currentMode === "dark" ? "Light" : "Dark"} mode`}
              >
                {currentMode === "dark" ? <Sun size={13} /> : <Moon size={13} />}
                <span>{currentMode === "dark" ? "Light" : "Dark"}</span>
              </button>
            </div>

            <div className="quick-theme-list">
              {THEMES.map((t) => {
                const isActive = currentTheme === t.id;
                return (
                  <button
                    key={t.id}
                    className={`quick-theme-item ${isActive ? "active" : ""}`}
                    onClick={() => {
                      handleSelectTheme(t.id);
                      setOpen(false);
                    }}
                  >
                    <span className="theme-color-dot" style={{ backgroundColor: t.accent }} />
                    <div className="quick-theme-labels">
                      <strong>{t.name}</strong>
                      <small>{t.subtitle}</small>
                    </div>
                    {isActive && <Check size={14} className="active-check" />}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function ThemeSettingsPanel() {
  const [currentTheme, setCurrentTheme] = useState(getStoredTheme());
  const [currentMode, setCurrentMode] = useState(getStoredMode());
  const [currentAccent, setCurrentAccent] = useState(getStoredAccent());

  useEffect(() => {
    const handleThemeChange = (e) => {
      setCurrentTheme(e.detail.theme);
      setCurrentMode(e.detail.mode);
      setCurrentAccent(e.detail.accent);
    };
    window.addEventListener("onecrm-theme-changed", handleThemeChange);
    return () => window.removeEventListener("onecrm-theme-changed", handleThemeChange);
  }, []);

  const handleSelectTheme = (themeId) => {
    applyTheme(themeId, currentMode, currentAccent);
  };

  const handleSelectMode = (mode) => {
    applyTheme(currentTheme, mode, currentAccent);
  };

  const handleSelectAccent = (accentId) => {
    applyTheme(currentTheme, currentMode, accentId);
  };

  return (
    <div className="theme-settings-panel">
      <div className="theme-section">
        <div className="theme-section-head">
          <div>
            <h3>Theme Presets</h3>
            <p>Select your preferred corporate styling and brand feel.</p>
          </div>
        </div>

        <div className="theme-cards-grid">
          {THEMES.map((t) => {
            const isActive = currentTheme === t.id;
            return (
              <div
                key={t.id}
                className={`theme-card ${isActive ? "theme-card-active" : ""}`}
                onClick={() => handleSelectTheme(t.id)}
              >
                <div
                  className="theme-card-preview"
                  style={{
                    backgroundColor: t.previewBg,
                    borderColor: t.previewBorder,
                  }}
                >
                  <div
                    className="theme-preview-sidebar"
                    style={{ borderColor: t.previewBorder }}
                  >
                    <div className="theme-preview-bar" />
                    <div className="theme-preview-item active" style={{ backgroundColor: t.accent + "22", color: t.accent }} />
                    <div className="theme-preview-item" />
                    <div className="theme-preview-item" />
                  </div>
                  <div className="theme-preview-content">
                    <div
                      className="theme-preview-header"
                      style={{ borderColor: t.previewBorder }}
                    />
                    <div
                      className="theme-preview-card"
                      style={{
                        backgroundColor: t.previewCard,
                        borderColor: t.previewBorder,
                      }}
                    >
                      <div className="theme-preview-pill" style={{ backgroundColor: t.accent }} />
                      <div className="theme-preview-line w-long" />
                      <div className="theme-preview-line w-short" />
                    </div>
                  </div>
                </div>

                <div className="theme-card-footer">
                  <div className="theme-card-meta">
                    <div className="theme-title-row">
                      <span className="theme-badge-color" style={{ backgroundColor: t.accent }} />
                      <strong>{t.name}</strong>
                    </div>
                    <p>{t.description}</p>
                  </div>
                  {isActive ? (
                    <span className="theme-active-tag">
                      <Check size={13} /> Active
                    </span>
                  ) : (
                    <span className="theme-select-btn">Select</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="theme-options-split">
        <div className="theme-section mode-section">
          <div className="theme-section-head">
            <div>
              <h3>Appearance Mode</h3>
              <p>Choose between daytime clarity or low-light comfort.</p>
            </div>
          </div>

          <div className="mode-toggle-group">
            <button
              className={`mode-btn ${currentMode === "light" ? "active" : ""}`}
              onClick={() => handleSelectMode("light")}
            >
              <Sun size={17} />
              <div>
                <strong>Light Appearance</strong>
                <small>Optimal for bright daytime environments</small>
              </div>
              {currentMode === "light" && <Check size={16} className="mode-check" />}
            </button>

            <button
              className={`mode-btn ${currentMode === "dark" ? "active" : ""}`}
              onClick={() => handleSelectMode("dark")}
            >
              <Moon size={17} />
              <div>
                <strong>Dark Appearance</strong>
                <small>High contrast, reduced glare & battery efficient</small>
              </div>
              {currentMode === "dark" && <Check size={16} className="mode-check" />}
            </button>
          </div>
        </div>

        <div className="theme-section accent-section">
          <div className="theme-section-head">
            <div>
              <h3>Accent Color Highlight</h3>
              <p>Personalize interactive focus rings, active tabs, and primary action buttons.</p>
            </div>
          </div>

          <div className="accent-swatches-grid">
            {ACCENTS.map((acc) => {
              const isActive = currentAccent === acc.id;
              return (
                <button
                  key={acc.id}
                  className={`accent-swatch-item ${isActive ? "active" : ""}`}
                  onClick={() => handleSelectAccent(acc.id)}
                >
                  <span
                    className="accent-swatch-circle"
                    style={{
                      backgroundColor: acc.color === "inherit" ? "var(--primary)" : acc.color,
                    }}
                  >
                    {isActive && <Check size={12} color="#fff" />}
                  </span>
                  <span>{acc.name}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
