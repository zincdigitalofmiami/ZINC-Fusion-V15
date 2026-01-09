'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  X, 
  Settings, 
  Database, 
  Cpu, 
  Activity, 
  GitBranch, 
  Users, 
  Shield, 
  LogOut 
} from 'lucide-react';

interface QuantAdminSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onLogout?: () => void;
}

export function QuantAdminSidebar({ isOpen, onClose, onLogout }: QuantAdminSidebarProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />

          {/* Sidebar */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed top-0 right-0 bottom-0 w-80 bg-[#0a0a0a] border-l border-white/10 shadow-2xl z-50 flex flex-col"
          >
            {/* Header */}
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white tracking-tight">QUANT ADMIN</h2>
                <div className="text-[10px] text-slate-500 font-mono uppercase">System Control Plane</div>
              </div>
              <button 
                onClick={onClose}
                className="p-2 hover:bg-white/5 rounded-full text-slate-400 hover:text-white transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Menu Items */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
               
               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-2 mb-1">
                   Core Infrastructure
               </div>
               
               <MenuItem icon={<Database size={16} />} label="Database Health" status="Healthy" />
               <MenuItem icon={<Cpu size={16} />} label="Model Registry" status="Active" />
               <MenuItem icon={<Activity size={16} />} label="Job Status" status="Idle" />

               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-6 mb-1">
                   Configuration
               </div>

               <MenuItem icon={<GitBranch size={16} />} label="Feature Flags" />
               <MenuItem icon={<Settings size={16} />} label="Global Config" />
               <MenuItem icon={<Shield size={16} />} label="Access Control" />
               
               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-6 mb-1">
                   User Management
               </div>
               
               <MenuItem icon={<Users size={16} />} label="Team Profiles" />
               
            </div>

            {/* Footer / User Profile */}
            <div className="p-4 border-t border-white/5 bg-zinc-900/30">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 border border-white/10 flex items-center justify-center text-white font-bold">
                        CM
                    </div>
                    <div>
                        <div className="text-sm font-bold text-white">Chris Mitchell</div>
                        <div className="text-xs text-slate-500">Head of Quant Strategy</div>
                    </div>
                </div>
                
                <button 
                    onClick={onLogout}
                    className="w-full flex items-center justify-center gap-2 p-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-bold rounded-lg border border-red-500/20 transition-colors"
                >
                    <LogOut size={14} />
                    SIGNOUT SYSTEM
                </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function MenuItem({ icon, label, status }: { icon: React.ReactNode, label: string, status?: string }) {
    return (
        <button className="w-full flex items-center justify-between p-3 rounded-lg hover:bg-white/5 text-slate-300 hover:text-white transition-all group">
            <div className="flex items-center gap-3">
                <div className="text-slate-500 group-hover:text-blue-400 transition-colors">{icon}</div>
                <span className="text-sm font-medium">{label}</span>
            </div>
            {status && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    status === 'Healthy' || status === 'Active' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                    'bg-slate-500/10 text-slate-500 border-slate-500/20'
                }`}>
                    {status}
                </span>
            )}
        </button>
    )
}
