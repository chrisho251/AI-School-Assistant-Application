/* KitchenSink — dev-only gallery of every UI primitive, for eyeballing against
 * design_files/ui_kits/asag-friendly/index.html. Mounted at /__kitchensink only
 * in dev builds (see App.tsx). Not part of the product surface. */
import { useState } from 'react';

import { Icon } from '@/components/Icon';
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Citation,
  IconButton,
  Input,
  ProgressBar,
  RadioGroup,
  Select,
  SourceChip,
  Spinner,
  StatusPill,
  Textarea,
  type BadgeTone,
} from '@/components/ui';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 36 }}>
      <h3 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-strong)', marginBottom: 14 }}>
        {title}
      </h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center' }}>
        {children}
      </div>
    </section>
  );
}

const BADGE_TONES: BadgeTone[] = [
  'neutral',
  'brand',
  'success',
  'warning',
  'danger',
  'info',
  'ai',
  'student',
  'teacher',
];

const STATUSES = [
  'ready',
  'finalised',
  'published',
  'draft',
  'ingesting',
  'grading',
  'submitted',
  'unknown',
];

export function KitchenSink() {
  const [radio, setRadio] = useState('A');
  const [activeCite, setActiveCite] = useState(false);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fr-page)', padding: '40px 48px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-strong)', marginBottom: 4 }}>
          Primitives kitchen sink
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5, marginBottom: 32 }}>
          Dev-only reference — compare against the design mock.
        </p>

        <Section title="Buttons — variants">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="soft">Soft</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button disabled>Disabled</Button>
        </Section>

        <Section title="Buttons — sizes + icons">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
          <Button iconLeft={<Icon name="plus" size={16} />}>New notebook</Button>
          <Button variant="soft" iconRight={<Icon name="arrowRight" size={16} />}>
            Continue
          </Button>
          <IconButton label="Notifications">
            <Icon name="bell" size={19} />
          </IconButton>
        </Section>

        <Section title="Badges">
          {BADGE_TONES.map((t) => (
            <Badge key={t} tone={t} dot>
              {t}
            </Badge>
          ))}
          <Badge tone="brand" solid>
            solid
          </Badge>
        </Section>

        <Section title="Avatars">
          <Avatar name="Ho Duy Hoang" role="teacher" size={40} />
          <Avatar name="Mai Lan" role="student" size={40} />
          <Avatar role="ai" size={40} />
          <Avatar name="No Role" size={40} />
        </Section>

        <Section title="Spinner">
          <Spinner size={17} color="var(--fr-accent)" />
          <Spinner size={24} color="var(--fr-accent)" />
        </Section>

        <Section title="Status pills">
          {STATUSES.map((s) => (
            <StatusPill key={s} status={s} />
          ))}
        </Section>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 36 }}>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Inputs</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Input
                label="Email"
                placeholder="you@school.edu"
                iconLeft={<Icon name="fileText" size={15} />}
              />
              <Textarea placeholder="Write an answer…" rows={3} />
              <Select
                options={[
                  { value: 'easy', label: 'Easy' },
                  { value: 'medium', label: 'Medium' },
                  { value: 'hard', label: 'Hard' },
                ]}
              />
            </div>
          </div>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>RadioGroup</h3>
            <RadioGroup
              value={radio}
              onChange={setRadio}
              options={[
                { value: 'A', key: 'A', label: 'Row Level Security' },
                { value: 'B', key: 'B', label: 'Remote Login Service' },
                { value: 'C', key: 'C', label: 'Rapid Load Sharing' },
              ]}
            />
          </div>
        </div>

        <Section title="Progress bars">
          <div style={{ width: 220 }}>
            <ProgressBar value={35} tone="brand" />
          </div>
          <div style={{ width: 220 }}>
            <ProgressBar value={70} tone="success" />
          </div>
          <div style={{ width: 220 }}>
            <ProgressBar value={90} tone="ai" />
          </div>
        </Section>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 36 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700 }}>Alerts</h3>
          <Alert tone="info" title="Heads up" icon={<Icon name="alert" size={16} />}>
            Grounded answers come only from your class materials.
          </Alert>
          <Alert tone="warning" title="Lockdown mode" icon={<Icon name="shield" size={16} />}>
            Leaving this tab is recorded for your teacher.
          </Alert>
          <Alert tone="ai" title="ASAG is writing" icon={<Icon name="sparkles" size={16} />}>
            Generating a grounded quiz from your sources…
          </Alert>
        </div>

        <Section title="Cards">
          <Card style={{ width: 260 }}>
            <b style={{ color: 'var(--text-strong)' }}>Plain card</b>
            <p style={{ margin: '6px 0 0', fontSize: 13.5 }}>Resting surface.</p>
          </Card>
          <Card interactive style={{ width: 260 }}>
            <b style={{ color: 'var(--text-strong)' }}>Interactive</b>
            <p style={{ margin: '6px 0 0', fontSize: 13.5 }}>Hover to lift 3px.</p>
          </Card>
          <Card accent="ai" style={{ width: 260 }}>
            <b style={{ color: 'var(--text-strong)' }}>AI accent</b>
            <p style={{ margin: '6px 0 0', fontSize: 13.5 }}>Violet left border.</p>
          </Card>
        </Section>

        <Section title="Citation + SourceChip">
          <p style={{ fontSize: 14.5, color: 'var(--text-body)', maxWidth: 420 }}>
            Photosynthesis stores energy as glucose
            <Citation n={1} active={activeCite} onClick={() => setActiveCite((v) => !v)} /> in the
            chloroplast
            <Citation n={2} />.
          </p>
          <div style={{ width: 300, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <SourceChip
              index={1}
              filename="biology-ch3.pdf"
              locator="p.12"
              type="pdf"
              active={activeCite}
              onClick={() => setActiveCite((v) => !v)}
            />
            <SourceChip index={2} filename="leaf-cross-section.png" locator="fig. 4" type="image" />
          </div>
        </Section>
      </div>
    </div>
  );
}
