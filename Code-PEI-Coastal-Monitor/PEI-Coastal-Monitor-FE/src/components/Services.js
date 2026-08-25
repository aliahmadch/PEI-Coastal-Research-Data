import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  MdGpsFixed, MdSatellite, MdShowChart, MdTimeline,
  MdBarChart, MdLayers, MdArrowForward, MdWaves, MdRocketLaunch
} from 'react-icons/md';

const stats = [
  { value: 'Satellite', label: 'Imagery', icon: MdSatellite },
  { value: 'High-res', label: 'Analysis', icon: MdGpsFixed },
  { value: 'Water', label: 'Detection', icon: MdWaves },
  { value: 'Transect', label: 'Method', icon: MdShowChart },
];

const SERVICES = [
  { 
    Icon: MdGpsFixed, 
    tag: '01', 
    title: 'Study Area Selection', 
    desc: 'Define coastal zones using predefined PEI boundaries or draw custom polygons on the interactive map.', 
    gradient: 'from-cyan-400 to-cyan-600',
    bgGradient: 'from-cyan-50 to-cyan-100'
  },
  { 
    Icon: MdSatellite, 
    tag: '02', 
    title: 'Satellite Imagery', 
    desc: 'Load true-colour and land-water masks for baseline and comparison periods. Shorelines extracted automatically.', 
    gradient: 'from-blue-400 to-blue-600',
    bgGradient: 'from-blue-50 to-blue-100'
  },
  { 
    Icon: MdShowChart, 
    tag: '03', 
    title: 'Erosion & Accretion', 
    desc: 'Quantify coastal land change between two time periods with area change in km² and percentage.', 
    gradient: 'from-teal-400 to-teal-600',
    bgGradient: 'from-teal-50 to-teal-100'
  },
  { 
    Icon: MdTimeline, 
    tag: '04', 
    title: 'Shoreline Change Transects', 
    desc: 'Generate shore-perpendicular transects and compute shoreline change rates with per-transect metrics.', 
    gradient: 'from-indigo-400 to-indigo-600',
    bgGradient: 'from-indigo-50 to-indigo-100'
  },
  { 
    Icon: MdBarChart, 
    tag: '05', 
    title: 'Charts & Reports', 
    desc: 'Interactive coastal change charts. Export summaries to CSV or generate a PDF report for documentation.', 
    gradient: 'from-violet-400 to-violet-600',
    bgGradient: 'from-violet-50 to-violet-100'
  },
  { 
    Icon: MdLayers, 
    tag: '06', 
    title: 'Layered Map View', 
    desc: 'Toggle imagery layers, erosion overlays, transects, and study boundaries for clear spatial interpretation.', 
    gradient: 'from-sky-400 to-sky-600',
    bgGradient: 'from-sky-50 to-sky-100'
  },
];

const Services = () => (
  <div className="min-h-screen w-full bg-gradient-to-br from-blue-50 via-white to-cyan-50 overflow-x-hidden overflow-y-auto">

    {/* Hero Section */}
    <section className="relative overflow-hidden bg-gradient-to-br from-blue-500 via-cyan-500 to-blue-600 py-16 sm:py-20 md:py-24 px-4 sm:px-6">
      
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-64 h-64 bg-white rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob"></div>
        <div className="absolute top-40 right-10 w-64 h-64 bg-cyan-200 rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
        <div className="absolute -bottom-20 left-1/2 w-64 h-64 bg-blue-200 rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob animation-delay-4000"></div>
      </div>

      <div className="relative max-w-4xl mx-auto text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-white/20 backdrop-blur-sm border border-white/30 text-white text-xs font-bold tracking-wide uppercase px-4 py-2 rounded-full mb-6 shadow-lg">
          <MdSatellite size={16} /> GIS & Remote Sensing Platform
        </div>

        {/* Title */}
        <h1 className="text-3xl sm:text-4xl md:text-6xl font-extrabold text-white leading-tight tracking-tight mb-6 px-2 drop-shadow-lg">
          Coastal Monitoring
          <span className="block mt-2 text-transparent bg-clip-text bg-gradient-to-r from-cyan-100 to-white">
            Powered by Satellite Data
          </span>
        </h1>

        <p className="text-white/90 text-base sm:text-lg md:text-xl max-w-2xl mx-auto leading-relaxed px-2 mb-8">
          A university research tool for satellite-based shoreline change detection and coastal erosion analysis along Prince Edward Island.
        </p>

        {/* CTA Button */}
        <NavLink
          to="/dashboard"
          className="inline-flex items-center gap-3 px-8 py-4 bg-white text-blue-600 font-bold text-lg rounded-xl shadow-2xl hover:shadow-3xl hover:-translate-y-1 transition-all duration-300 group"
        >
          <MdRocketLaunch className="text-2xl group-hover:rotate-12 transition-transform duration-300" />
          Launch Dashboard
          <MdArrowForward className="text-xl group-hover:translate-x-1 transition-transform duration-300" />
        </NavLink>
      </div>

      {/* Stats bar */}
      <div className="relative max-w-4xl mx-auto mt-12 sm:mt-16 grid grid-cols-2 sm:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <div key={i} className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl px-4 py-5 text-center hover:bg-white/20 transition-all duration-300 hover:-translate-y-1 shadow-lg">
            <s.icon className="text-white text-3xl mx-auto mb-2" />
            <p className="text-white font-bold text-lg sm:text-xl leading-tight">{s.value}</p>
            <p className="text-white/70 text-xs sm:text-sm mt-1 uppercase tracking-wide leading-tight">{s.label}</p>
          </div>
        ))}
      </div>
    </section>

    {/* Services Cards Section */}
    <section className="w-full px-4 sm:px-6 py-16 sm:py-20">
      <div className="text-center mb-12 sm:mb-16 animate-fade-in">
        <div className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-100 to-cyan-100 px-4 py-2 rounded-full mb-4">
          <MdLayers className="text-blue-600 text-lg" />
          <span className="text-sm font-bold text-blue-700 tracking-wide uppercase">Platform Capabilities</span>
        </div>
        
        <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900 mb-4">
          Everything You Need for
          <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-600">
            Coastal Analysis
          </span>
        </h2>
        
        <p className="text-gray-600 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
          Analyze, visualize, and report coastal change from satellite imagery with our comprehensive toolkit.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 w-full max-w-7xl mx-auto">
        {SERVICES.map(({ Icon, tag, title, desc, gradient, bgGradient }, i) => (
          <div
            key={i}
            className="group relative bg-white rounded-3xl p-8 border-2 border-gray-100 hover:border-transparent shadow-lg hover:shadow-2xl transition-all duration-500 hover:-translate-y-2 flex flex-col gap-4 overflow-hidden"
          >
            {/* Gradient background on hover */}
            <div className={`absolute inset-0 bg-gradient-to-br ${bgGradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`}></div>
            
            {/* Content */}
            <div className="relative z-10">
              <div className="flex items-start justify-between mb-4">
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${gradient} flex items-center justify-center text-white shadow-lg group-hover:scale-110 group-hover:rotate-6 transition-all duration-500`}>
                  <Icon size={28} />
                </div>
                <span className="text-gray-200 group-hover:text-gray-300 font-black text-3xl leading-none select-none transition-colors duration-300">{tag}</span>
              </div>
              
              <h3 className="text-gray-900 font-bold text-xl mb-3 group-hover:text-gray-800 transition-colors duration-300">{title}</h3>
              <p className="text-gray-600 text-base leading-relaxed group-hover:text-gray-700 transition-colors duration-300">{desc}</p>
            </div>

            {/* Decorative corner element */}
            <div className={`absolute -bottom-6 -right-6 w-24 h-24 bg-gradient-to-br ${gradient} rounded-full opacity-0 group-hover:opacity-10 blur-2xl transition-opacity duration-500`}></div>
          </div>
        ))}
      </div>
    </section>

    {/* CTA Section */}
    <section className="w-full px-4 sm:px-6 pb-16 sm:pb-20">
      <div className="w-full max-w-5xl mx-auto">
        <div className="relative rounded-3xl overflow-hidden bg-gradient-to-r from-blue-500 via-cyan-500 to-blue-600 p-8 sm:p-12 shadow-2xl">
          
          {/* Background pattern */}
          <div className="absolute inset-0 opacity-10">
            <div className="absolute inset-0" style={{
              backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
              backgroundSize: '40px 40px'
            }}></div>
          </div>

          <div className="relative flex flex-col sm:flex-row items-center justify-between gap-6 text-center sm:text-left">
            <div>
              <h3 className="text-white font-extrabold text-2xl sm:text-3xl mb-3">
                Ready to Analyze the Coastline?
              </h3>
              <p className="text-white/90 text-base sm:text-lg max-w-xl">
                Open the dashboard and start your first satellite-based coastal analysis today.
              </p>
            </div>
            
            <NavLink
              to="/dashboard"
              className="flex-shrink-0 inline-flex items-center gap-3 px-8 py-4 bg-white text-blue-600 font-bold text-lg rounded-xl shadow-2xl hover:shadow-3xl hover:-translate-y-1 transition-all duration-300 group whitespace-nowrap"
            >
              Open Dashboard
              <MdArrowForward className="text-xl group-hover:translate-x-2 transition-transform duration-300" />
            </NavLink>
          </div>
        </div>
      </div>
    </section>

    <style jsx>{`
      @keyframes blob {
        0%, 100% { transform: translate(0, 0) scale(1); }
        25% { transform: translate(20px, -50px) scale(1.1); }
        50% { transform: translate(-20px, 20px) scale(0.9); }
        75% { transform: translate(50px, 50px) scale(1.05); }
      }
      
      @keyframes fade-in {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
      }
      
      .animate-blob {
        animation: blob 7s infinite;
      }
      
      .animation-delay-2000 {
        animation-delay: 2s;
      }
      
      .animation-delay-4000 {
        animation-delay: 4s;
      }
      
      .animate-fade-in {
        animation: fade-in 0.6s ease-out;
      }
    `}</style>

  </div>
);

export default Services;
