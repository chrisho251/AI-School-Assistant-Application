/* Icon — maps the mock's custom icon names to lucide-react components.
 *
 * The design kit used its own <Icon name="…"/> registry (fr-icons.jsx). We keep
 * that call signature so screens port ~1:1, but render real lucide-react icons.
 */
import {
  ArrowRight,
  Bell,
  Book,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Clock,
  Code,
  Download,
  Eye,
  FileText,
  Flag,
  GraduationCap,
  Home,
  Image,
  Layers,
  Lock,
  LogOut,
  Maximize,
  MessageCircle,
  Notebook,
  PanelLeft,
  PartyPopper,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  Shield,
  Smile,
  Sparkles,
  Star,
  Target,
  Trash2,
  TriangleAlert,
  Trophy,
  Upload,
  Users,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import type { CSSProperties } from 'react';

const ICONS = {
  book: Book,
  notebook: Notebook,
  chat: MessageCircle,
  quiz: ClipboardCheck,
  shield: Shield,
  lock: Lock,
  upload: Upload,
  plus: Plus,
  search: Search,
  send: Send,
  refresh: RefreshCw,
  check: Check,
  x: X,
  chevronRight: ChevronRight,
  chevronDown: ChevronDown,
  sparkles: Sparkles,
  cap: GraduationCap,
  fileText: FileText,
  image: Image,
  code: Code,
  clock: Clock,
  alert: TriangleAlert,
  eye: Eye,
  logout: LogOut,
  panelLeft: PanelLeft,
  settings: Settings,
  arrowRight: ArrowRight,
  maximize: Maximize,
  flag: Flag,
  star: Star,
  smile: Smile,
  users: Users,
  layers: Layers,
  trophy: Trophy,
  zap: Zap,
  bookOpen: BookOpen,
  helpCircle: CircleHelp,
  target: Target,
  bell: Bell,
  home: Home,
  penLine: PenLine,
  trash: Trash2,
  download: Download,
  messageCircle: MessageCircle,
  partyPopper: PartyPopper,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: CSSProperties;
}

export function Icon({
  name,
  size = 18,
  color = 'currentColor',
  strokeWidth = 2,
  style,
}: IconProps) {
  const Cmp = ICONS[name];
  return (
    <Cmp
      size={size}
      color={color}
      strokeWidth={strokeWidth}
      style={{ display: 'block', flex: 'none', ...style }}
    />
  );
}
