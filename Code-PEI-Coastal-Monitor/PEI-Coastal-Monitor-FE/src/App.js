import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import Home from './components/Home';
import Services from './components/Services';
import Contact from './components/Contact';
import DeveloperBoard from './components/DeveloperBoard';
import { MdMenu, MdClose, MdHome, MdDashboard, MdMiscellaneousServices, MdPeople, MdEmail, MdWaves } from 'react-icons/md';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';

function AppInner() {
  const location = useLocation();
  const onDashboard = location.pathname === '/dashboard';
  const [menuOpen, setMenuOpen] = useState(false);
  const [visitorCount, setVisitorCount] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/warmup`, {
      method: 'POST',
      cache: 'no-store',
      keepalive: true,
    }).catch(() => {});

    const tracked = sessionStorage.getItem('visit_tracked');
    if (!tracked) {
      fetch(`${API_BASE}/visitors/track`, { method: 'POST' })
        .then(r => r.json())
        .then(d => { setVisitorCount(d.total); sessionStorage.setItem('visit_tracked', '1'); })
        .catch(() => {});
    } else {
      fetch(`${API_BASE}/visitors`)
        .then(r => r.json())
        .then(d => setVisitorCount(d.total))
        .catch(() => {});
    }
  }, []);

  const navLinks = [
    { to: '/', label: 'Home', end: true, icon: MdHome },
    { to: '/dashboard', label: 'Dashboard', icon: MdDashboard },
    { to: '/services', label: 'Services', icon: MdMiscellaneousServices },
    { to: '/developers', label: 'Developers', icon: MdPeople },
    { to: '/contact', label: 'Contact', icon: MdEmail },
  ];

  return (
    <>
      <nav className="sticky top-0 z-50 bg-white shadow-sm border-b border-gray-200">
        
        <div className="relative w-full px-3 sm:px-4 lg:px-8">
          <div className="flex items-center justify-between py-1.5 min-h-[48px]">

            {/* Simple Logo Design */}
            <NavLink to="/" className="flex items-center gap-3 group flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 flex items-center justify-center">
                  <img
                    src={process.env.PUBLIC_URL + 'upei-logo.png'}
                    alt=""
                    className="w-full h-full object-contain"
                  />
                </div>

                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-800 font-bold text-xl tracking-tight whitespace-nowrap leading-none">
                      PEI Coastal Monitor
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <MdWaves className="text-blue-500 text-xs" />
                    <span className="text-gray-500 text-xs font-medium tracking-wide">
                      Coastal Erosion Analytics
                    </span>
                  </div>
                </div>
              </div>
            </NavLink>

            {/* Simple Desktop Navigation */}
            <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
              {navLinks.map(({ to, label, end, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `px-4 py-2 rounded-lg text-base font-semibold transition-all duration-200 whitespace-nowrap flex items-center gap-2 ${
                      isActive
                        ? 'text-blue-600 bg-blue-50'
                        : 'text-gray-600 hover:text-blue-600 hover:bg-gray-50'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={`text-lg ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
              {visitorCount !== null && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-100 ml-2">
                  <span className="text-base">👥</span>
                  <span className="text-blue-700 text-xs font-bold whitespace-nowrap">{visitorCount.toLocaleString()}</span>
                </div>
              )}
            </div>
            <div className="lg:hidden flex items-center gap-2 flex-shrink-0">
              {visitorCount !== null && (
                <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-blue-50 border border-blue-100">
                  <span className="text-sm">👥</span>
                  <span className="text-blue-700 text-xs font-bold">{visitorCount.toLocaleString()}</span>
                </div>
              )}
              <button
                onClick={() => setMenuOpen(!menuOpen)}
                className="text-gray-600 p-2 rounded-lg hover:bg-gray-100 transition-all duration-200"
                aria-label="Toggle menu"
              >
                {menuOpen ? <MdClose size={24} /> : <MdMenu size={24} />}
              </button>
            </div>
          </div>
        </div>

        {/* Simple Mobile Menu */}
        {menuOpen && (
          <div className="lg:hidden border-t border-gray-200 bg-white px-4 py-4 shadow-lg">
            <div className="flex flex-col gap-2">
              {navLinks.map(({ to, label, end, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) =>
                    `px-4 py-3 rounded-lg text-base font-semibold transition-all duration-200 flex items-center gap-3 ${
                      isActive
                        ? 'text-blue-600 bg-blue-50'
                        : 'text-gray-600 hover:text-blue-600 hover:bg-gray-50'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={`text-xl ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </nav>

      <style jsx>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        @keyframes wave {
          0% { background-position: 0 0; }
          100% { background-position: 100px 0; }
        }
        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .animate-gradient {
          background-size: 200% auto;
          animation: gradient 3s ease infinite;
        }
        .animate-spin-slow {
          animation: spin 8s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>

      <main>
        {/* Dashboard is always mounted so Leaflet + analysis state survive navigation */}
        <div style={{ display: onDashboard ? 'block' : 'none' }}>
          <Dashboard />
        </div>

        {!onDashboard && (
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/home" element={<Home />} />
            <Route path="/services" element={<Services />} />
            <Route path="/developers" element={<DeveloperBoard />} />
            <Route path="/contact" element={<Contact />} />
          </Routes>
        )}
      </main>

      {!onDashboard && (
      <footer className="relative bg-gradient-to-br from-gray-50 to-blue-50 border-t border-gray-200 overflow-hidden">
        
        {/* Decorative top line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-blue-400 to-transparent opacity-50" />
        
        {/* Subtle background pattern */}
        <div className="absolute inset-0 opacity-[0.02] pointer-events-none" style={{
          backgroundImage: 'linear-gradient(#3b82f6 1px, transparent 1px), linear-gradient(90deg, #3b82f6 1px, transparent 1px)',
          backgroundSize: '40px 40px'
        }} />
        
        <div className="relative w-full px-4 sm:px-6 lg:px-12 py-8">
          <div className="max-w-7xl mx-auto">
            
            {/* Main footer content */}
            <div className="flex flex-col lg:flex-row items-center justify-between gap-6 mb-6">

              {/* Logo Section */}
              <div className="flex items-center gap-3 flex-shrink-0 group">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 flex items-center justify-center">
                    <img
                      src={process.env.PUBLIC_URL + 'upei-logo.png'}
                      alt=""
                      className="w-full h-full object-contain"
                    />
                  </div>

                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-800 font-bold text-xl tracking-tight whitespace-nowrap leading-none">
                        PEI Coastal Monitor
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <MdWaves className="text-blue-500 text-xs" />
                      <span className="text-gray-500 text-xs font-medium tracking-wide">
                        Coastal Erosion Analytics
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Navigation Links */}
              <div className="flex flex-wrap items-center justify-center gap-6 lg:gap-8">
                {[
                  { to: '/', label: 'Home', icon: MdHome },
                  { to: '/services', label: 'Services', icon: MdMiscellaneousServices },
                  { to: '/developers', label: 'Developers', icon: MdPeople },
                  { to: '/contact', label: 'Contact', icon: MdEmail }
                ].map(({ to, label, icon: Icon }) => (
                  <NavLink 
                    key={to} 
                    to={to} 
                    className="group flex items-center gap-2 text-gray-600 hover:text-blue-600 text-sm font-semibold transition-all duration-300 relative"
                  >
                    <Icon className="text-base group-hover:scale-110 transition-transform duration-300" />
                    {label}
                    <span className="absolute -bottom-1 left-0 w-0 h-[2px] bg-blue-600 group-hover:w-full transition-all duration-300" />
                  </NavLink>
                ))}
              </div>

            </div>

            {/* Divider */}
            <div className="h-[1px] bg-gradient-to-r from-transparent via-gray-300 to-transparent mb-6" />

            {/* Bottom section */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left">
              <p className="text-gray-600 text-sm leading-relaxed">
                © {new Date().getFullYear()} PEI Coastal Monitor. All rights reserved.
                <span className="hidden sm:inline"> • </span>
                <span className="block sm:inline text-blue-600 font-medium">Prince Edward Island, Canada</span>
              </p>
              
              <div className="flex items-center gap-3 flex-wrap justify-center">
                {visitorCount !== null && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 border border-blue-100">
                    <span className="text-blue-500 text-sm">👥</span>
                    <span className="text-blue-700 text-xs font-bold">{visitorCount.toLocaleString()} visitors</span>
                  </div>
                )}
                <span className="text-gray-500 text-xs font-semibold tracking-wider uppercase">Powered by</span>
                <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-200 shadow-sm">
                  <span className="text-blue-600 text-xs font-bold">GIS</span>
                  <span className="text-gray-300">•</span>
                  <span className="text-cyan-600 text-xs font-bold">Satellite Imagery</span>
                  <span className="text-gray-300">•</span>
                  <span className="text-blue-600 text-xs font-bold">Shoreline Detection</span>
                </div>
              </div>
            </div>

          </div>
        </div>
      </footer>
      )}
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}

export default App;
