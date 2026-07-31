import { useState, ReactNode } from 'react';

interface CollapsibleSectionProps {
  title: string;
  icon?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: ReactNode;
}

export default function CollapsibleSection({
  title,
  icon,
  defaultOpen = true,
  children,
  badge,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden shadow-sm mb-3 transition-all duration-300">
      {/* Header - Always visible */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 bg-gray-50/50 hover:bg-gray-100/50 flex items-center justify-between transition-all duration-300 group"
      >
        <div className="flex items-center gap-2">
          {icon && (
            <span className="w-7 h-7 bg-[#1977cc]/10 rounded-full flex items-center justify-center text-sm group-hover:bg-[#1977cc]/20 transition-all duration-300">
              {icon}
            </span>
          )}
          <span className="text-sm font-semibold text-[#2c4964] font-heading uppercase tracking-wider">
            {title}
          </span>
          {badge}
        </div>
        <span
          className={`text-[#1977cc] transition-transform duration-300 ${
            isOpen ? 'rotate-180' : 'rotate-0'
          }`}
        >
          ▼
        </span>
      </button>

      {/* Content - Collapsible */}
      <div
        className={`transition-all duration-300 ease-in-out overflow-hidden ${
          isOpen ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="p-4 bg-white">
          {children}
        </div>
      </div>
    </div>
  );
}
