import React from 'react';
import { FaGithub, FaLinkedin } from 'react-icons/fa';
import { MdEmail, MdLocationOn, MdCode, MdPeople, MdRocket } from 'react-icons/md';

const team = [
  {
    image: require('../images/prof. farooque.jpeg'),
    initials: 'AF',
    name: 'Aitazaz A Farooque',
    role: 'Prof. of Precision Agriculture',
    tag: 'Research Lead',
    location: 'Charlottetown, CA',
    email: 'afarooque@upei.ca',
    bio: 'Guides the research direction for satellite imagery, coastal monitoring, and applied geospatial analysis.',
    skills: ['Research leadership', 'Precision agriculture', 'Remote sensing', 'Coastal monitoring', 'Geospatial analysis'],
    gradient: 'from-cyan-400 to-blue-500',
    bgColor: 'bg-cyan-50',
    github: '#',
    linkedin: 'https://www.linkedin.com/in/aitazaz-a-farooque-phd-p-eng-a87792257/',
  },
  {
    image: require('../images/aliahmad_img-modified (1).png'),
    initials: 'AA',
    name: 'Ali Ahmad',
    role: 'GIS & Remote Sensing',
    tag: 'Development Lead',
    location: 'Charlottetown, CA',
    email: 'aahmad19761@upei.ca',
    bio: 'Specializes in shoreline extraction and transect-based coastal change analysis. Translates satellite imagery into meaningful coastal change metrics.',
    skills: ['Coastal analysis', 'Shoreline detection', 'Transect analysis', 'Map workflows', 'Remote sensing'],
    gradient: 'from-violet-400 to-purple-500',
    bgColor: 'bg-violet-50',
    github: 'https://github.com/aliahmadch',
    linkedin: 'https://www.linkedin.com/in/ali-ahmad-b-eng-660370244/',
  },
  {
    image: require('../images/modassir.jpeg'),
    initials: 'MM',
    name: 'Mohammad Modassir',
    role: 'GIS & Remote Sensing',
    tag: 'GIS Developer',
    location: 'Islamabad, PAK',
    email: 'mohammadmudasir681@gmail.com',
    bio: 'Develops erosion modelling pipelines and statistical analysis workflows. Bridges the gap between raw satellite imagery and actionable environmental insights.',
    skills: ['Erosion modelling', 'Data analysis', 'Cloud processing', 'Environmental insights', 'Remote sensing'],
    gradient: 'from-teal-400 to-cyan-500',
    bgColor: 'bg-teal-50',
    github: 'https://github.com/modasir321',
    linkedin: 'https://www.linkedin.com/in/modasir-rafique-1b216a261/',
  },
  {
    image: require('../images/shamas.jpeg'),
    initials: 'SR',
    name: 'Shamas Ur Rehman',
    role: 'Software Developer',
    tag: 'Design & Frontend',
    location: 'Kasur, PAK',
    email: 'shamasurrehman398@gmail.com',
    bio: 'Designs and builds intuitive interfaces for complex geospatial tools. Ensures the platform is accessible and visually clear for researchers and students.',
    skills: ['Interface design', 'Frontend delivery', 'Visual systems', 'User experience', 'Accessibility'],
    gradient: 'from-pink-400 to-rose-500',
    bgColor: 'bg-pink-50',
    github: 'https://github.com/Shamas-Ur-Rehman',
    linkedin: 'https://www.linkedin.com/in/shamas-ur-rehman-4219a4243/',
  },
];

const stack = [
  { name: 'Interface Layer', cat: 'Frontend', icon: 'UI' },
  { name: 'Visual System', cat: 'Styling', icon: 'VS' },
  { name: 'Map Workspace', cat: 'Mapping', icon: 'MW' },
  { name: 'Analysis API', cat: 'Backend', icon: 'API' },
  { name: 'Satellite Imagery', cat: 'Imagery', icon: 'SI' },
  { name: 'Cloud Processing', cat: 'Processing', icon: 'CP' },
  { name: 'Shoreline Detection', cat: 'Detection', icon: 'SD' },
  { name: 'Change Metrics', cat: 'Analysis', icon: 'CM' },
];

const DeveloperBoard = () => (
  <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 overflow-x-hidden overflow-y-auto">

    {/* Hero Section */}
    <section className="relative overflow-hidden bg-gradient-to-br from-blue-500 via-cyan-500 to-blue-600 py-16 sm:py-20 md:py-24 px-4">
      
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-64 h-64 bg-white rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob"></div>
        <div className="absolute top-40 right-10 w-64 h-64 bg-cyan-200 rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
        <div className="absolute -bottom-20 left-1/2 w-64 h-64 bg-blue-200 rounded-full mix-blend-overlay filter blur-3xl opacity-20 animate-blob animation-delay-4000"></div>
      </div>

      <div className="relative max-w-4xl mx-auto text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-white/20 backdrop-blur-sm border border-white/30 text-white text-xs font-bold tracking-wide uppercase px-4 py-2 rounded-full mb-6 shadow-lg">
          <MdPeople size={16} /> University Research Team
        </div>

        {/* Title */}
        <h1 className="text-3xl sm:text-4xl md:text-6xl font-extrabold text-white leading-tight tracking-tight mb-6 px-2 drop-shadow-lg">
          Meet the
          <span className="block mt-2 text-transparent bg-clip-text bg-gradient-to-r from-cyan-100 to-white">
            Developer Board
          </span>
        </h1>

        <p className="text-white/90 text-base sm:text-lg md:text-xl max-w-2xl mx-auto leading-relaxed px-2 mb-8">
          A multidisciplinary team from UPEI and other universities combining GIS, remote sensing, and modern web engineering to monitor PEI's coastline.
        </p>

        {/* Stats bar */}
        <div className="max-w-3xl mx-auto grid grid-cols-3 gap-4">
          {[
            { v: team.length, l: 'Developers', icon: MdPeople },
            { v: stack.length, l: 'Technologies', icon: MdCode },
            { v: '2024', l: 'Project Year', icon: MdRocket }
          ].map((s, i) => (
            <div key={i} className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl px-4 py-5 text-center hover:bg-white/20 transition-all duration-300 hover:-translate-y-1 shadow-lg">
              <s.icon className="text-white text-3xl mx-auto mb-2" />
              <p className="text-white font-bold text-xl sm:text-2xl leading-tight">{s.v}</p>
              <p className="text-white/70 text-xs sm:text-sm mt-1 uppercase tracking-wide">{s.l}</p>
            </div>
          ))}
        </div>
      </div>
    </section>

    {/* Team Cards Section */}
    <section className="w-full px-4 sm:px-6 py-16 sm:py-20">
      <div className="text-center mb-12 sm:mb-16 animate-fade-in">
        <div className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-100 to-cyan-100 px-4 py-2 rounded-full mb-4">
          <MdPeople className="text-blue-600 text-lg" />
          <span className="text-sm font-bold text-blue-700 tracking-wide uppercase">Our Team</span>
        </div>
        
        <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900 mb-4">
          Researchers & Engineers
          <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-600">
            Building the Future
          </span>
        </h2>
        
        <p className="text-gray-600 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
          Working at the intersection of geospatial science and software development.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 max-w-5xl mx-auto">
        {team.map((dev, i) => (
          <div
            key={i}
            className="group bg-white rounded-3xl overflow-hidden border-2 border-gray-100 hover:border-transparent shadow-lg hover:shadow-2xl transition-all duration-500 hover:-translate-y-2 flex flex-col sm:flex-row"
          >
            {/* Photo / Avatar area */}
            <div className={`relative h-56 sm:h-auto sm:w-56 md:w-64 flex-shrink-0 flex items-center justify-center overflow-hidden ${dev.bgColor}`}>
              
              {dev.image ? (
                <img
                  src={dev.image}
                  alt={dev.name}
                  className="w-32 h-32 rounded-full object-cover ring-4 ring-white shadow-xl group-hover:scale-110 transition-transform duration-500"
                />
              ) : (
                <div className={`w-32 h-32 rounded-full flex items-center justify-center text-white font-black text-4xl ring-4 ring-white shadow-xl bg-gradient-to-br ${dev.gradient} group-hover:scale-110 group-hover:rotate-6 transition-all duration-500`}>
                  {dev.initials}
                </div>
              )}

              {/* Role tag badge */}
              <span className={`absolute bottom-4 left-1/2 -translate-x-1/2 text-xs font-bold px-4 py-1.5 rounded-full whitespace-nowrap shadow-lg bg-gradient-to-r ${dev.gradient} text-white`}>
                {dev.tag}
              </span>
            </div>

            {/* Card body */}
            <div className="p-6 sm:p-8 flex min-w-0 flex-col gap-5 flex-1">
              {/* Name + socials */}
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <h3 className="text-gray-900 font-bold text-2xl sm:text-3xl leading-tight whitespace-nowrap">{dev.name}</h3>
                  <p className={`text-lg sm:text-xl font-semibold mt-2 bg-gradient-to-r ${dev.gradient} bg-clip-text text-transparent whitespace-nowrap`}>
                    {dev.role}
                  </p>
                </div>
                <div className="flex gap-3 flex-shrink-0">
                  <a 
                    href={dev.github} 
                    className="w-12 h-12 rounded-xl bg-gray-100 hover:bg-gray-900 flex items-center justify-center text-gray-600 hover:text-white transition-all duration-300 shadow-sm hover:shadow-md" 
                    aria-label="GitHub"
                  >
                    <FaGithub size={20} />
                  </a>
                  <a 
                    href={dev.linkedin} 
                    className="w-12 h-12 rounded-xl bg-gray-100 hover:bg-blue-600 flex items-center justify-center text-gray-600 hover:text-white transition-all duration-300 shadow-sm hover:shadow-md" 
                    aria-label="LinkedIn"
                  >
                    <FaLinkedin size={20} />
                  </a>
                </div>
              </div>

              {/* Meta */}
              <div className="space-y-4">
                <div className="flex items-center gap-4 text-gray-500 text-xl whitespace-nowrap">
                  <MdLocationOn size={22} className="flex-shrink-0 text-gray-400" />
                  {dev.location}
                </div>
                <div className="flex items-center gap-4 text-gray-500 text-xl leading-relaxed whitespace-nowrap">
                  <MdEmail size={22} className="flex-shrink-0 text-gray-400" />
                  <a
                    href={`mailto:${dev.email}`}
                    className="min-w-0 flex-1 hover:text-blue-600 transition-colors"
                  >
                    {dev.email}
                  </a>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>

    {/* Tech Stack Section */}
    <section className="w-full px-4 sm:px-6 pb-16 sm:pb-20">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-12 animate-fade-in">
          <div className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-100 to-cyan-100 px-4 py-2 rounded-full mb-4">
            <MdCode className="text-blue-600 text-lg" />
            <span className="text-sm font-bold text-blue-700 tracking-wide uppercase">Tech Stack</span>
          </div>
          
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900 mb-4">
            Powered by
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-600">
              Modern Technology
            </span>
          </h2>
          
          <p className="text-gray-600 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
            Technologies powering the PEI Coastal Monitor platform.
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {stack.map((t, i) => (
            <div 
              key={i} 
              className="group bg-white hover:bg-gradient-to-br hover:from-blue-50 hover:to-cyan-50 border-2 border-gray-100 hover:border-blue-200 rounded-2xl px-6 py-6 text-center transition-all duration-300 hover:-translate-y-1 shadow-md hover:shadow-xl"
            >
              <div className="text-4xl mb-3 group-hover:scale-110 transition-transform duration-300">
                {t.icon}
              </div>
              <p className="text-gray-900 font-bold text-base mb-1">{t.name}</p>
              <p className="text-blue-600 text-xs font-semibold uppercase tracking-wide">{t.cat}</p>
            </div>
          ))}
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

export default DeveloperBoard;
