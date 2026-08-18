/* Avatar — initials on a role-tinted gradient; sparkles glyph for the AI role.
 * Ported from fr-ui.jsx (values kept identical). */
import { Icon } from '@/components/Icon';

export type AvatarRole = 'teacher' | 'student' | 'ai';

interface AvatarProps {
  name?: string;
  role?: AvatarRole;
  size?: number;
}

const GRADIENTS: Record<AvatarRole, string> = {
  teacher: 'linear-gradient(135deg,#fbbf24,#d97706)',
  student: 'linear-gradient(135deg,#2dd4bf,#0d9488)',
  ai: 'linear-gradient(135deg,#a78bfa,#7c3aed)',
};
const FALLBACK_GRADIENT = 'linear-gradient(135deg,#818cf8,#4f46e5)';

export function Avatar({ name = '', role, size = 34 }: AvatarProps) {
  const initials = name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  const bg = role ? GRADIENTS[role] : FALLBACK_GRADIENT;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: 999,
        background: bg,
        color: '#fff',
        fontSize: size * 0.4,
        fontWeight: 700,
        flex: 'none',
        boxShadow: '0 1px 2px rgba(15,23,42,.12), inset 0 0 0 1.5px rgba(255,255,255,.25)',
      }}
    >
      {role === 'ai' ? <Icon name="sparkles" size={size * 0.5} color="#fff" /> : initials}
    </span>
  );
}
