
import React from "react";
import {
  MapPin,
  Hospital,
  House,
  ShieldAlert,
  Database,
} from "lucide-react";

export default function SafetyPlacesPanel() {
  return (
    <section className="safety-places-panel">
      <div className="safety-panel-header">
        <div>
          <h2>
            <MapPin size={22} />
            Safety Locations & Emergency Facilities
          </h2>
          <p>
            GIS-based facility information for disaster
            decision support
          </p>
        </div>

        <span className="safety-data-status">
          <Database size={14} />
          Data Not Connected
        </span>
      </div>

      <div className="safety-facility-grid">
        <div className="safety-facility-card">
          <div className="safety-facility-icon">
            <Hospital size={25} />
          </div>

          <h3>Hospitals & Medical Facilities</h3>
          <p>
            Verified hospital coordinates, accessibility,
            service availability, and capacity information
            have not yet been connected.
          </p>

          <span>0 verified records loaded</span>
        </div>

        <div className="safety-facility-card">
          <div className="safety-facility-icon">
            <House size={25} />
          </div>

          <h3>Emergency Shelters</h3>
          <p>
            Verified shelter locations, current operating
            status, available capacity, and hazard exposure
            have not yet been connected.
          </p>

          <span>0 verified records loaded</span>
        </div>
      </div>

      <div className="safety-data-requirements">
        <h3>Required Data for Future Integration</h3>

        <p>
          The planned safety-location module requires
          georeferenced hospital and shelter datasets,
          administrative boundaries, verified facility
          status, and relevant accessibility information.
        </p>
      </div>

      <div className="safety-warning">
        <ShieldAlert size={21} />

        <p>
          <strong>Research prototype limitation:</strong>{" "}
          No facility is currently confirmed as a safe or
          operational evacuation destination. This panel
          must not be used for real-world evacuation routing
          or emergency decisions.
        </p>
      </div>
    </section>
  );
}
