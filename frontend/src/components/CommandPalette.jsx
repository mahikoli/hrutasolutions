import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Search, ArrowRight, LayoutDashboard, Target, Building2, ContactRound,
  BriefcaseBusiness, FileText, ListTodo, Activity, CircleDollarSign,
  GraduationCap, UsersRound, FolderKanban, LifeBuoy, Settings,
  BarChart3, ShieldCheck, Sun, Moon, Palette, Plus, X, Sparkles
} from "lucide-react";
import { THEMES, applyTheme, getStoredMode, getStoredTheme } from "../theme";

export default function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  onCreate,
  canSell,
  data = {},
  pageMeta = {},
}) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) onClose();
        else onClose(false); // open handled by parent
      } else if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Build searchable items
  const items = useMemo(() => {
    const list = [];

    // Navigation items
    Object.entries(pageMeta).forEach(([key, meta]) => {
      const Icon = meta.icon || LayoutDashboard;
      list.push({
        id: `nav-${key}`,
        category: "Navigation",
        label: meta.label,
        subtext: `Go to ${meta.title || meta.label}`,
        icon: Icon,
        action: () => {
          onNavigate(key);
          onClose();
        },
      });
    });

    // Quick Actions
    if (onCreate) {
      if (canSell) {
        list.push({
          id: "act-lead",
          category: "Quick Actions",
          label: "Create New Lead",
          subtext: "Add prospective customer into the pipeline",
          icon: Plus,
          action: () => {
            onCreate("lead");
            onClose();
          },
        });
        list.push({
          id: "act-contact",
          category: "Quick Actions",
          label: "Add New Contact",
          subtext: "Store a new customer or stakeholder contact",
          icon: Plus,
          action: () => {
            onCreate("contact");
            onClose();
          },
        });
        list.push({
          id: "act-org",
          category: "Quick Actions",
          label: "Add New Organization",
          subtext: "Create client, partner, or college company",
          icon: Plus,
          action: () => {
            onCreate("organization");
            onClose();
          },
        });
      }
      list.push({
        id: "act-task",
        category: "Quick Actions",
        label: "Create New Task",
        subtext: "Schedule an action item with due date",
        icon: Plus,
        action: () => {
          onCreate("task");
          onClose();
        },
      });
      list.push({
        id: "act-activity",
        category: "Quick Actions",
        label: "Log Activity",
        subtext: "Record call, meeting, email or interaction note",
        icon: Plus,
        action: () => {
          onCreate("activity");
          onClose();
        },
      });
    }

    // Theme & Mode Actions
    const currentMode = getStoredMode();
    list.push({
      id: "theme-toggle-mode",
      category: "Theme & Appearance",
      label: currentMode === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode",
      subtext: `Current mode: ${currentMode}`,
      icon: currentMode === "dark" ? Sun : Moon,
      action: () => {
        applyTheme(undefined, currentMode === "dark" ? "light" : "dark");
        onClose();
      },
    });

    THEMES.forEach((t) => {
      list.push({
        id: `theme-${t.id}`,
        category: "Theme & Appearance",
        label: `Theme: ${t.name}`,
        subtext: t.description,
        icon: Palette,
        action: () => {
          applyTheme(t.id);
          onClose();
        },
      });
    });

    // Quick Record Search from current data
    if (data.leads?.length) {
      data.leads.slice(0, 15).forEach((lead) => {
        const leadName = [lead.first_name, lead.last_name].filter(Boolean).join(" ") || lead.full_name || "Lead";
        list.push({
          id: `record-lead-${lead.id}`,
          category: "Leads",
          label: leadName,
          subtext: `${lead.organization_name ? lead.organization_name + " · " : ""}${lead.status || "new"} · #${lead.id}`,
          icon: Target,
          action: () => {
            onNavigate("leads");
            onClose();
          },
        });
      });
    }

    if (data.organizations?.length) {
      data.organizations.slice(0, 10).forEach((org) => {
        list.push({
          id: `record-org-${org.id}`,
          category: "Organizations",
          label: org.name,
          subtext: `${org.industry ? org.industry + " · " : ""}${org.organization_type || "client"}`,
          icon: Building2,
          action: () => {
            onNavigate("organizations");
            onClose();
          },
        });
      });
    }

    return list;
  }, [pageMeta, onCreate, canSell, data, onNavigate, onClose]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.subtext.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
    );
  }, [items, query]);

  // Adjust selection when filtered list changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredItems.length]);

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, filteredItems.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filteredItems.length) % Math.max(1, filteredItems.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredItems[selectedIndex]) {
        filteredItems[selectedIndex].action();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="cmd-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
    >
      <div className="cmd-panel" onKeyDown={handleKeyDown}>
        <div className="cmd-header">
          <Search size={18} className="cmd-search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="cmd-input"
            placeholder="Type a command, module, or search records..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="cmd-clear" onClick={() => setQuery("")} title="Clear search">
              <X size={15} />
            </button>
          )}
          <span className="cmd-badge">ESC to close</span>
        </div>

        <div className="cmd-body">
          {filteredItems.length === 0 ? (
            <div className="cmd-empty">
              <Sparkles size={24} className="cmd-empty-icon" />
              <p>No results found for "{query}"</p>
              <span>Try searching for modules, leads, tasks, or theme settings.</span>
            </div>
          ) : (
            filteredItems.map((item, index) => {
              const isSelected = index === selectedIndex;
              const Icon = item.icon;
              return (
                <div
                  key={item.id}
                  className={`cmd-item ${isSelected ? "selected" : ""}`}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onClick={() => item.action()}
                >
                  <div className="cmd-item-icon">
                    <Icon size={16} />
                  </div>
                  <div className="cmd-item-info">
                    <div className="cmd-item-top">
                      <span className="cmd-item-title">{item.label}</span>
                      <span className="cmd-item-category">{item.category}</span>
                    </div>
                    <span className="cmd-item-desc">{item.subtext}</span>
                  </div>
                  {isSelected && (
                    <div className="cmd-item-arrow">
                      <ArrowRight size={14} />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="cmd-footer">
          <div className="cmd-keys">
            <span><kbd>↑</kbd> <kbd>↓</kbd> Navigate</span>
            <span><kbd>↵</kbd> Select</span>
            <span><kbd>ESC</kbd> Close</span>
          </div>
          <div className="cmd-branding">
            <span>HRUTA OneCRM</span>
          </div>
        </div>
      </div>
    </div>
  );
}
