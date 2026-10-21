
import {
  LayoutDashboard,
  Map,
  Users,
  BrainCircuit,
  Siren,
  MapPin,
  ChartNoAxesCombined,
  ShieldAlert,
} from "lucide-react";

const menuItems = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "gis", label: "GIS Risk Map", icon: Map },
  { id: "human-impact", label: "Human Impact", icon: Users },
  { id: "ml-analysis", label: "ML & SHAP Analysis", icon: BrainCircuit },
  { id: "decisions", label: "Immediate Decisions", icon: Siren },
  { id: "safety", label: "Safety Locations", icon: MapPin },
  {
    id: "timeline",
    label: "Forecast Timeline",
    icon: ChartNoAxesCombined,
  },
];

export default function Sidebar({ activePage = "overview", onNavigate }) {
  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <ShieldAlert size={27} />
        </div>

        <div>
          <h2>Disaster Intelligence</h2>
          <p>Research Decision Support</p>
        </div>
      </div>

      <div className="sidebar-section-label">NAVIGATION</div>

      <nav className="sidebar-navigation" aria-label="Dashboard navigation">
        {menuItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`sidebar-menu-item ${
              activePage === id ? "active" : ""
            }`}
            onClick={() => onNavigate?.(id)}
            aria-current={activePage === id ? "page" : undefined}
          >
            <Icon size={19} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <ShieldAlert size={16} />
        <span>Research prototype — not an official warning system</span>
      </div>
    </aside>
  );
}
