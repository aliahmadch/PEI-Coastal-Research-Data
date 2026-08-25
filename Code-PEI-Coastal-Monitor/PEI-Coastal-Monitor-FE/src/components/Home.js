import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import img1 from '../images/img1.jpg';
import img2 from '../images/img2.jpg';
import img3 from '../images/img3.jpg';
import './Home.css';

const Home = () => {
  const images = [img1, img2, img3];
  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentImageIndex((prevIndex) => (prevIndex + 1) % images.length);
    }, 5000); // Change image every 5 seconds

    return () => clearInterval(interval);
  }, [images.length]);

  const features = [
    { icon: 'bi bi-geo-alt', title: 'Study areas & patches', description: 'Predefined PEI coastal regions and study-line boundaries for consistent analysis.', gradient: 'from-cyan-400 to-cyan-600', bgGradient: 'from-cyan-50 to-cyan-100' },
    { icon: 'bi bi-images', title: 'Satellite imagery', description: 'Baseline and comparison composites with true colour and shoreline detection layers.', gradient: 'from-blue-400 to-blue-600', bgGradient: 'from-blue-50 to-blue-100' },
    { icon: 'bi bi-graph-up-arrow', title: 'Erosion & accretion', description: 'Land area change between two dates with summary statistics and visual layers.', gradient: 'from-teal-400 to-teal-600', bgGradient: 'from-teal-50 to-teal-100' },
    { icon: 'bi bi-signpost-split', title: 'Change transects', description: 'Shoreline change rates along transects; click any transect for detailed change data.', gradient: 'from-indigo-400 to-indigo-600', bgGradient: 'from-indigo-50 to-indigo-100' }
  ];

  const stats = [
    { value: '1,100+', label: 'km PEI coastline' },
    { value: '5', label: 'study regions' },
    { value: 'Satellite', label: 'imagery source' },
    { value: 'Water', label: 'shoreline detection' }
  ];

  return (
    <div className="home-page">
      {/* Hero Section */}
      <section className="home-hero" style={{ backgroundImage: `linear-gradient(rgba(59, 130, 246, 0.85), rgba(6, 182, 212, 0.85)), url(${images[currentImageIndex]})` }}>
        {/* Animated background blobs */}
        <div className="home-hero-blobs">
          <div className="home-blob home-blob-1"></div>
          <div className="home-blob home-blob-2"></div>
          <div className="home-blob home-blob-3"></div>
        </div>

        <div className="home-hero-inner">
          <div className="home-hero-badge">
            <i className="bi bi-globe2" aria-hidden="true" />
            Prince Edward Island Coastal Monitoring
          </div>
          <h1 className="home-hero-title">
            Monitor Shoreline Change
            <span className="home-hero-title-gradient">
              with Satellite Data
            </span>
          </h1>
          <p className="home-hero-sub">
            Use baseline and comparison imagery, shoreline detection, and transect-based change analysis to assess erosion and accretion along PEI's coast.
          </p>
          <div className="home-hero-cta">
            <NavLink to="/dashboard" className="home-btn home-btn-primary">
              <i className="bi bi-speedometer2" aria-hidden="true" />
              Open Dashboard
              <i className="bi bi-arrow-right" aria-hidden="true" />
            </NavLink>
            <NavLink to="/services" className="home-btn home-btn-secondary">
              <i className="bi bi-info-circle" aria-hidden="true" />
              Learn More
            </NavLink>
          </div>
        </div>

        {/* Stats bar */}
        <div className="home-stats-bar">
          {stats.map((s, i) => (
            <div key={i} className="home-stat-item">
              <span className="home-stat-value">{s.value}</span>
              <span className="home-stat-label">{s.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Capabilities Section */}
      <section className="home-section home-how">
        <div className="home-container">
          <div className="home-section-header">
            <div className="home-section-badge">
              <i className="bi bi-layers" />
              Platform Capabilities
            </div>
            <h2 className="home-section-title">
              What you can do
              <span className="home-section-title-gradient">with the Dashboard</span>
            </h2>
            <p className="home-section-lead">
              Tools and data available for coastal analysis.
            </p>
          </div>
          <div className="home-features-grid">
            {features.map((f, i) => (
              <div key={i} className="home-feature-card">
                <div className={`home-feature-bg bg-gradient-to-br ${f.bgGradient}`}></div>
                <div className="home-feature-content">
                  <div className={`home-feature-icon-wrap bg-gradient-to-br ${f.gradient}`}>
                    <i className={`${f.icon} home-feature-icon`} aria-hidden="true" />
                  </div>
                  <h3 className="home-feature-title">{f.title}</h3>
                  <p className="home-feature-desc">{f.description}</p>
                </div>
                <div className={`home-feature-corner bg-gradient-to-br ${f.gradient}`}></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="home-section home-cta-wrap">
        <div className="home-container">
          <div className="home-cta-inner">
            <div className="home-cta-pattern"></div>
            <div className="home-cta-content">
              <div>
                <h2 className="home-cta-title">Ready to analyze PEI's coast?</h2>
                <p className="home-cta-text">Open the dashboard to select an area, load imagery, and run erosion and shoreline change analysis.</p>
              </div>
              <NavLink to="/dashboard" className="home-btn home-btn-primary home-btn-lg">
                <i className="bi bi-speedometer2" aria-hidden="true" />
                Go to Dashboard
                <i className="bi bi-arrow-right" aria-hidden="true" />
              </NavLink>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
