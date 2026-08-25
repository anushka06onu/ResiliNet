import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { getTopology } from '../services/api';

interface NetworkMapProps {
  onSelectElement: (element: any) => void;
}

const NetworkMap: React.FC<NetworkMapProps> = ({ onSelectElement }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initGraph = async () => {
      try {
        const topoData = await getTopology();
        
        if (!containerRef.current) return;

        // Transform data for cytoscape
        const elements: cytoscape.ElementDefinition[] = [];
        
        topoData.nodes.forEach((n: any) => {
          elements.push({
            data: { id: n.id, label: n.id, type: n.type }
          });
        });

        topoData.links.forEach((l: any, idx: number) => {
          elements.push({
            data: { id: `e${idx}`, source: l.source, target: l.target }
          });
        });

        const cy = cytoscape({
          container: containerRef.current,
          elements: elements,
          style: [
            {
              selector: 'node',
              style: {
                'background-color': '#0ea5e9', // sky-500
                'background-opacity': 0.8,
                'label': 'data(label)',
                'color': '#cbd5e1',
                'font-size': '11px',
                'font-family': 'Outfit, sans-serif',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 6,
                'width': 28,
                'height': 28,
                'border-width': 2,
                'border-color': '#38bdf8',
                'overlay-opacity': 0,
                'transition-property': 'background-color, border-color, border-width, width, height',
                'transition-duration': 300
              }
            },
            {
              selector: 'node[type="switch"]',
              style: {
                'shape': 'hexagon',
                'background-color': '#6366f1', // indigo-500
                'border-color': '#818cf8',
                'width': 36,
                'height': 36
              }
            },
            {
              selector: 'edge',
              style: {
                'width': 2.5,
                'line-color': '#334155', // slate-700
                'curve-style': 'bezier',
                'target-arrow-shape': 'none',
                'overlay-opacity': 0,
                'transition-property': 'line-color, width',
                'transition-duration': 300
              }
            },
            {
              selector: 'node:selected',
              style: {
                'border-width': 4,
                'border-color': '#10b981', // emerald-500
                'background-color': '#059669',
                'width': 40,
                'height': 40
              }
            },
            {
              selector: 'edge:selected',
              style: {
                'width': 5,
                'line-color': '#10b981' // emerald-500
              }
            }
          ],
          layout: {
            name: 'cose',
            padding: 80,
            nodeRepulsion: () => 8000,
            idealEdgeLength: () => 100,
            edgeElasticity: () => 100,
            animate: true,
            animationDuration: 1000,
            animationEasing: 'ease-out'
          },
          wheelSensitivity: 0.2
        });

        // Hover effects
        cy.on('mouseover', 'node', (e) => {
          document.body.style.cursor = 'pointer';
        });
        cy.on('mouseout', 'node', (e) => {
          document.body.style.cursor = 'default';
        });

        cy.on('tap', 'node, edge', function (evt) {
          onSelectElement({
            id: evt.target.id(),
            type: evt.target.isNode() ? 'node' : 'edge',
            data: evt.target.data()
          });
        });

        cy.on('tap', function (evt) {
          if (evt.target === cy) {
            onSelectElement(null);
          }
        });

        cyRef.current = cy;
        setLoading(false);
      } catch (e) {
        console.error("Failed to load topology", e);
        setLoading(false);
      }
    };

    initGraph();

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
      }
    };
  }, [onSelectElement]);

  return (
    <div className="w-full h-full relative">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 backdrop-blur-md z-20">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"></div>
            <div className="text-emerald-400 font-mono text-sm uppercase tracking-widest animate-pulse">Initializing Topology...</div>
          </div>
        </div>
      )}
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
};

export default NetworkMap;
