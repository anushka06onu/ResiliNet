import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../layout/Layout';
import { useStore } from '../../store/useStore';

describe('Layout component', () => {
  it('renders prominent simulation banner when in DEMO DATA or SIMULATION mode', () => {
    useStore.setState({ dataMode: 'SIMULATION' });
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.getByText('⚠️ SIMULATION DATA — NOT LIVE EXPERIMENTAL EVIDENCE')).toBeDefined();
  });

  it('renders prominent live lab banner when in LIVE LAB mode', () => {
    useStore.setState({ dataMode: 'LIVE LAB' });
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.getByText('🟢 LIVE LAB — ACTIVE SDN TELEMETRY')).toBeDefined();
  });
});
