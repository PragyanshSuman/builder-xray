import { en, type Strings } from './en';

export type Locale = 'en';

const locales: Record<Locale, Strings> = { en };

export function t(locale: Locale = 'en'): Strings {
  return locales[locale];
}
