import alex from '../assets/avatars/alex.svg';
import flake from '../assets/avatars/flake.svg';
import jordan from '../assets/avatars/jordan.svg';
import maya from '../assets/avatars/maya.svg';
import priya from '../assets/avatars/priya.svg';
import sam from '../assets/avatars/sam.svg';

const SRC: Record<string, string> = { alex, sam, priya, jordan, maya, flake };

export const displayName = (who: string) => (who === 'flake' ? 'Flake' : who ? who[0].toUpperCase() + who.slice(1) : who);

export function Avatar({ who, size = 'md' }: { who: string; size?: 'md' | 'lg' }) {
  const key = who.toLowerCase();
  return <img className={`avatar ${size === 'lg' ? 'lg' : ''}`} src={SRC[key] ?? flake} alt={displayName(who)} title={displayName(who)} />;
}
