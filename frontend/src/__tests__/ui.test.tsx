import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Badge, Button, Citation, SourceChip, StatusPill } from '@/components/ui';

describe('Button', () => {
  it('fires onClick when enabled', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    fireEvent.click(screen.getByText('Go'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('does not fire onClick when disabled', () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    fireEvent.click(screen.getByText('Go'));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('StatusPill', () => {
  it('maps known statuses to a label', () => {
    render(<StatusPill status="ingesting" />);
    expect(screen.getByText('Ingesting')).toBeInTheDocument();
  });

  it('maps submitted to "Awaiting review"', () => {
    render(<StatusPill status="submitted" />);
    expect(screen.getByText('Awaiting review')).toBeInTheDocument();
  });

  it('falls back to the raw status when unknown', () => {
    render(<StatusPill status="mystery" />);
    expect(screen.getByText('mystery')).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders its label', () => {
    render(
      <Badge tone="ai" dot>
        Draft
      </Badge>,
    );
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });
});

describe('Citation + SourceChip', () => {
  it('renders the marker number and fires onClick', () => {
    const onClick = vi.fn();
    render(<Citation n={3} onClick={onClick} />);
    const marker = screen.getByText('3');
    fireEvent.click(marker);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('renders the source filename + locator', () => {
    render(<SourceChip index={1} filename="biology-ch3.pdf" locator="p.12" type="pdf" />);
    expect(screen.getByText('biology-ch3.pdf')).toBeInTheDocument();
    expect(screen.getByText('p.12')).toBeInTheDocument();
  });
});
