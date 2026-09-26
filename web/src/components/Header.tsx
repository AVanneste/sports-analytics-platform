import React from 'react';
import { Trophy } from 'lucide-react';

interface HeaderProps {
  sport: 'football' | 'tennis';
  setSport: (sport: 'football' | 'tennis') => void;
  lastUpdated?: string;
}

export const Header: React.FC<HeaderProps> = ({ sport, setSport, lastUpdated }) => {
  return (
    <header className="border-b border-dark-700/80 bg-dark-800/80 backdrop-blur-md sticky top-0 z-50 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 via-teal-500 to-sky-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Trophy className="w-5 h-5 text-dark-900 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-base tracking-tight text-white">OmniVision AI</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                v2.4 PRO
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-500/10 text-sky-300 border border-sky-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400 mr-1.5 animate-pulse"></span>
                Live Feeds Active
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium">PitchVision & CourtVision Dual Predictive Engine</p>
          </div>
        </div>

        {/* Sport Switcher */}
        <div className="flex items-center space-x-2">
          <div className="flex bg-dark-900/80 p-1 rounded-xl border border-dark-700">
            <button
              onClick={() => setSport('football')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                sport === 'football' ? 'bg-emerald-500 text-dark-900 shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>⚽</span>
              <span>Football</span>
            </button>
            <button
              onClick={() => setSport('tennis')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                sport === 'tennis' ? 'bg-sky-500 text-dark-900 shadow-md' : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🎾</span>
              <span>Tennis</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
