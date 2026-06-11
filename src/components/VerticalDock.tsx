import { type ReactNode, useState } from 'react';
import { motion } from 'motion/react';

type DockItemData = {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
};

type VerticalDockProps = {
  items: DockItemData[];
};

export function VerticalDock({ items }: VerticalDockProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <nav className="dockShell" aria-label="Основная навигация">
      <div className="dockBrand">
        <span>FN</span>
      </div>
      <div className="dockRail" role="toolbar" aria-label="Разделы приложения">
        {items.map((item, index) => {
          const isLifted = hoveredIndex === index;

          return (
            <motion.button
              key={item.label}
              type="button"
              className={`dockButton${item.active ? ' isActive' : ''}`}
              onClick={item.onClick}
              onHoverStart={() => setHoveredIndex(index)}
              onHoverEnd={() => setHoveredIndex(null)}
              onFocus={() => setHoveredIndex(index)}
              onBlur={() => setHoveredIndex(null)}
              animate={{
                width: isLifted ? 62 : 52,
                height: isLifted ? 62 : 52,
              }}
              transition={{ type: 'spring', mass: 0.12, stiffness: 170, damping: 15 }}
              aria-label={item.label}
              title={item.label}
            >
              <span className="dockIcon">{item.icon}</span>
            </motion.button>
          );
        })}
      </div>
      <div className="dockPulse" />
    </nav>
  );
}
