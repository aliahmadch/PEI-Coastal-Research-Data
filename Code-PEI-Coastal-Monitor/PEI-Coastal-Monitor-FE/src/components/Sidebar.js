import React from 'react';
import { MdLayers, MdImage, MdWaterDrop, MdTimeline, MdWarning } from 'react-icons/md';
import './Sidebar.css';

const layerConfig = {
  trueColor: {
    icon: MdImage,
    label: 'True Color',
    color: 'blue',
    description: 'Natural satellite view'
  },
  ndwi: {
    icon: MdWaterDrop,
    label: 'NDWI',
    color: 'cyan',
    description: 'Water detection index'
  },
  baseline: {
    icon: MdTimeline,
    label: 'Baseline',
    color: 'indigo',
    description: 'Reference shoreline'
  },
  erosion: {
    icon: MdWarning,
    label: 'Erosion',
    color: 'red',
    description: 'Change detection'
  }
};

const Sidebar = ({ activeLayers, toggleLayer, loadImagery, analyzeCoastalChange }) => {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-box">
          <img src={`${process.env.PUBLIC_URL || ''}/upei-logo.png`} alt="PEI" className="sidebar-logo" />
        </div>
        <div className="logo-text">
          <h2 className="logo-title">PEI Monitor</h2>
          <p className="logo-subtitle">Coastal Analysis</p>
        </div>
      </div>

      <div className="sidebar-section">
        <div className="section-header">
          <MdLayers className="section-icon" />
          <h3 className="section-title">Map Layers</h3>
        </div>
        
        <div className="layers-list">
          {Object.entries(layerConfig).map(([key, config]) => {
            const Icon = config.icon;
            const isActive = activeLayers.has(key);
            
            return (
              <label key={key} className={`layer-item ${isActive ? 'active' : ''}`}>
                <div className="layer-content">
                  <div className={`layer-icon-wrapper ${config.color}`}>
                    <Icon className="layer-icon" />
                  </div>
                  <div className="layer-info">
                    <span className="layer-label">{config.label}</span>
                    <span className="layer-description">{config.description}</span>
                  </div>
                </div>
                <div className="toggle-wrapper">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={() => toggleLayer(key)}
                    className="layer-checkbox"
                  />
                  <div className="toggle-slider"></div>
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* Uncomment when needed */}
      {/* <div className="sidebar-actions">
        <button onClick={loadImagery} className="btn-sidebar btn-primary">
          <MdImage /> Load Imagery
        </button>
        <button onClick={analyzeCoastalChange} className="btn-sidebar btn-secondary">
          <MdTimeline /> Analyze Changes
        </button>
      </div> */}

    </aside>
  );
};

export default Sidebar;
