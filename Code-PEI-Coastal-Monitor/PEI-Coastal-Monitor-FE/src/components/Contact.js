import React, { useState, useRef } from 'react';
import { MdEmail, MdLocationOn, MdAccessTime, MdSend, MdCheckCircle, MdPhone, MdWaves } from 'react-icons/md';
import emailjs from '@emailjs/browser';

const Contact = () => {
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const formRef = useRef();

  const handleSubmit = (e) => {
    e.preventDefault();
    setSending(true);
    setError('');
    const SERVICE_ID = 'service_rtjukn1';
    const TEMPLATE_ID = 'template_j79gomq';
    const PUBLIC_KEY = '3xH6bRku_em--hS5N';

    emailjs.sendForm(SERVICE_ID, TEMPLATE_ID, formRef.current, PUBLIC_KEY)
      .then((result) => {
        console.log('Email sent successfully:', result.text);
        setSubmitted(true);
        setSending(false);
        formRef.current.reset();
      })
      .catch((error) => {
        console.error('Email send failed:', error);
        setError(error?.text || 'Failed to send message. Please try again.');
        setSending(false);
      });
  };

  return (
    <div className="min-h-[calc(100vh-64px)] bg-gradient-to-br from-blue-50 via-white to-cyan-50 relative overflow-hidden">
      
      {/* Animated Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-72 h-72 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob"></div>
        <div className="absolute top-40 right-10 w-72 h-72 bg-cyan-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>
        <div className="absolute -bottom-20 left-1/2 w-72 h-72 bg-indigo-200 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-4000"></div>
        
        <div className="absolute bottom-0 left-0 right-0 h-32 opacity-10">
          <svg className="w-full h-full" viewBox="0 0 1200 120" preserveAspectRatio="none">
            <path d="M0,0 C150,100 350,0 600,50 C850,100 1050,0 1200,50 L1200,120 L0,120 Z" fill="url(#wave-gradient)"/>
            <defs>
              <linearGradient id="wave-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#3b82f6" />
                <stop offset="50%" stopColor="#06b6d4" />
                <stop offset="100%" stopColor="#3b82f6" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>

      <div className="relative max-w-7xl mx-auto px-4 py-12 sm:px-6 lg:px-8">
        
        <div className="text-center mb-12 animate-fade-in">
          <div className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-100 to-cyan-100 px-4 py-2 rounded-full mb-4 shadow-sm">
            <MdWaves className="text-blue-600 text-lg animate-pulse" />
            <span className="text-sm font-bold text-blue-700 tracking-wide uppercase">Get In Touch</span>
          </div>
          
          <h1 className="text-4xl md:text-5xl font-extrabold text-gray-900 mb-4 leading-tight">
            Let's Make Waves
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-600">
              Together
            </span>
          </h1>
          
          <p className="text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
            Have questions about coastal monitoring? Our team is ready to help you navigate the data.
          </p>
        </div>

        <div className="grid lg:grid-cols-3 gap-8 max-w-6xl mx-auto">
          
          <div className="lg:col-span-1 space-y-4">
            
            <div className="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 hover:border-blue-200 hover:-translate-y-1">
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-300">
                  <MdEmail className="text-white text-xl" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 mb-1 text-sm uppercase tracking-wide">Email Us</h3>
                  <p className="text-blue-600 font-semibold text-base">aahmad19761@upei.ca</p>
                  <p className="text-gray-500 text-xs mt-1">We'll respond within 24 hours</p>
                </div>
              </div>
            </div>

            <div className="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 hover:border-cyan-200 hover:-translate-y-1">
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-cyan-500 to-cyan-600 rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-300">
                  <MdPhone className="text-white text-xl" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 mb-1 text-sm uppercase tracking-wide">Call Us</h3>
                  <p className="text-cyan-600 font-semibold text-base">+1 (902) 314-7840</p>
                  <p className="text-gray-500 text-xs mt-1">Mon-Fri, 9AM-5PM AST</p>
                </div>
              </div>
            </div>

            <div className="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 hover:border-indigo-200 hover:-translate-y-1">
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-300">
                  <MdLocationOn className="text-white text-xl" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 mb-1 text-sm uppercase tracking-wide">Visit Us</h3>
                  <p className="text-indigo-600 font-semibold text-base">DSC-18, 550 University Avenue, Charlottetown, PE, C1A 4P3</p>
                  <p className="text-gray-500 text-xs mt-1">Canada</p>
                </div>
              </div>
            </div>

            <div className="bg-gradient-to-br from-blue-500 to-cyan-500 rounded-2xl p-6 shadow-xl text-white">
              <div className="flex items-center gap-3 mb-3">
                <MdAccessTime className="text-3xl" />
                <h3 className="font-bold text-lg">Quick Response</h3>
              </div>
              <p className="text-blue-50 text-sm leading-relaxed">
                Our team typically responds within 1-2 business days. For urgent matters, please call us directly.
              </p>
            </div>

          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-3xl shadow-2xl p-8 md:p-10 border border-gray-100">
              
              {submitted ? (
                <div className="text-center py-12 animate-fade-in">
                  <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-green-400 to-green-500 rounded-full mb-6 shadow-lg">
                    <MdCheckCircle className="text-white text-4xl" />
                  </div>
                  <h3 className="text-3xl font-bold text-gray-900 mb-3">Message Sent!</h3>
                  <p className="text-gray-600 text-lg mb-6 max-w-md mx-auto">
                    Thanks for reaching out. We'll get back to you within 1-2 business days.
                  </p>
                  <button
                    onClick={() => setSubmitted(false)}
                    className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 text-white font-semibold rounded-xl hover:from-blue-600 hover:to-cyan-600 transition-all duration-300 shadow-lg hover:shadow-xl"
                  >
                    Send Another Message
                  </button>
                </div>
              ) : (
                <>
                  <div className="mb-8">
                    <h2 className="text-3xl font-bold text-gray-900 mb-2">Send us a Message</h2>
                    <p className="text-gray-600">Fill out the form below and we'll get back to you shortly.</p>
                  </div>

                  <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
                    
                    {error && (
                      <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-3 rounded-lg animate-shake">
                        <p className="font-semibold">{error}</p>
                      </div>
                    )}
                    
                    <div className="grid md:grid-cols-2 gap-6">
                      <div className="group">
                        <label htmlFor="contact-name" className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                          Your Name *
                        </label>
                        <input
                          id="contact-name"
                          name="user_name"
                          type="text"
                          required
                          placeholder="John Doe"
                          className="w-full px-4 py-3 rounded-xl border-2 border-gray-200 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300 group-hover:border-gray-300"
                        />
                      </div>
                      
                      <div className="group">
                        <label htmlFor="contact-email" className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                          Email Address *
                        </label>
                        <input
                          id="contact-email"
                          name="user_email"
                          type="email"
                          required
                          placeholder="john@example.com"
                          className="w-full px-4 py-3 rounded-xl border-2 border-gray-200 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300 group-hover:border-gray-300"
                        />
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-6">
                      <div className="group">
                        <label htmlFor="contact-phone" className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                          Phone Number
                        </label>
                        <input
                          id="contact-phone"
                          name="user_phone"
                          type="tel"
                          placeholder="+1 (902) 555-0100"
                          className="w-full px-4 py-3 rounded-xl border-2 border-gray-200 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300 group-hover:border-gray-300"
                        />
                      </div>
                      
                      <div className="group">
                        <label htmlFor="contact-subject" className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                          Subject
                        </label>
                        <input
                          id="contact-subject"
                          name="subject"
                          type="text"
                          placeholder="How can we help?"
                          className="w-full px-4 py-3 rounded-xl border-2 border-gray-200 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300 group-hover:border-gray-300"
                        />
                      </div>
                    </div>

                    <div className="group">
                      <label htmlFor="contact-message" className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                        Your Message *
                      </label>
                      <textarea
                        id="contact-message"
                        name="message"
                        rows={5}
                        required
                        placeholder="Tell us more about your inquiry..."
                        className="w-full px-4 py-3 rounded-xl border-2 border-gray-200 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300 resize-none group-hover:border-gray-300"
                      />
                    </div>

                    <button
                      type="submit"
                      disabled={sending}
                      className="w-full py-4 px-8 bg-gradient-to-r from-blue-500 via-cyan-500 to-blue-500 bg-size-200 bg-pos-0 hover:bg-pos-100 text-white font-bold text-lg rounded-xl shadow-xl hover:shadow-2xl transition-all duration-500 hover:-translate-y-1 active:translate-y-0 flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed group"
                    >
                      {sending ? (
                        <>
                          <div className="w-5 h-5 border-3 border-white border-t-transparent rounded-full animate-spin"></div>
                          Sending...
                        </>
                      ) : (
                        <>
                          Send Message
                          <MdSend className="text-xl group-hover:translate-x-1 transition-transform duration-300" />
                        </>
                      )}
                    </button>
                  </form>
                </>
              )}
            </div>
          </div>

        </div>
      </div>

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
        
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-10px); }
          75% { transform: translateX(10px); }
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
        
        .animate-shake {
          animation: shake 0.5s ease-in-out;
        }
        
        .bg-size-200 {
          background-size: 200% auto;
        }
        
        .bg-pos-0 {
          background-position: 0% center;
        }
        
        .hover\\:bg-pos-100:hover {
          background-position: 100% center;
        }
      `}</style>
    </div>
  );
};

export default Contact;
