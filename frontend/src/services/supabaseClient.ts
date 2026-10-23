/**
 * supabaseClient.ts — Browser Supabase Auth & Client Service
 * ReStockIQ Real Authentication Integration
 *
 * Provides:
 * - Supabase JS client initialized with safe public anon key (VITE_SUPABASE_PUBLISHABLE_KEY).
 * - Email/password sign-up with safe default role ('planner').
 * - Email/password sign-in, sign-out, session restoration, and auth state change listeners.
 * - Graceful detection when Supabase is not configured (offline demo mode).
 * - Strict secret isolation: SUPABASE_SECRET_KEY is never imported or bundled.
 */

import { createClient, SupabaseClient, Session, User } from '@supabase/supabase-js';

const supabaseUrl = (import.meta as unknown as { env?: { VITE_SUPABASE_URL?: string } }).env?.VITE_SUPABASE_URL || '';
const supabaseAnonKey = (import.meta as unknown as { env?: { VITE_SUPABASE_PUBLISHABLE_KEY?: string } }).env?.VITE_SUPABASE_PUBLISHABLE_KEY || '';

const isConfigured = Boolean(
  supabaseUrl &&
  supabaseAnonKey &&
  supabaseUrl.startsWith('http') &&
  !supabaseUrl.includes('placeholder')
);

export const supabase: SupabaseClient | null = isConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export function isSupabaseConfigured(): boolean {
  return isConfigured && supabase !== null;
}

export interface AuthResponse {
  user: User | null;
  session: Session | null;
  error: string | null;
}

/**
 * Sign up a new user with email and password.
 * Safe Role Governance: All self-registered users are assigned the unprivileged 'planner' role.
 * Approver/admin roles require explicit assignment by an administrator.
 */
export async function signUpWithEmail(email: string, password: string): Promise<AuthResponse> {
  if (!supabase) {
    return { user: null, session: null, error: 'Supabase credentials are not configured in this environment.' };
  }

  try {
    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        data: {
          role: 'planner', // Default safe role
        },
      },
    });

    if (error) {
      return { user: null, session: null, error: error.message };
    }

    return { user: data.user, session: data.session, error: null };
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Registration failed unexpectedly.';
    return { user: null, session: null, error: msg };
  }
}

/**
 * Sign in existing user with email and password.
 */
export async function signInWithEmail(email: string, password: string): Promise<AuthResponse> {
  if (!supabase) {
    return { user: null, session: null, error: 'Supabase credentials are not configured in this environment.' };
  }

  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (error) {
      return { user: null, session: null, error: error.message };
    }

    return { user: data.user, session: data.session, error: null };
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Sign-in failed unexpectedly.';
    return { user: null, session: null, error: msg };
  }
}

/**
 * Sign out the currently authenticated user.
 */
export async function signOutUser(): Promise<{ error: string | null }> {
  if (!supabase) {
    return { error: null };
  }

  try {
    const { error } = await supabase.auth.signOut();
    return { error: error ? error.message : null };
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Sign-out failed.';
    return { error: msg };
  }
}

/**
 * Get the current active Supabase session.
 */
export async function getSupabaseSession(): Promise<Session | null> {
  if (!supabase) return null;
  try {
    const { data } = await supabase.auth.getSession();
    return data.session;
  } catch {
    return null;
  }
}

/**
 * Subscribe to Supabase authentication state changes.
 */
export function onSupabaseAuthStateChange(callback: (session: Session | null) => void): () => void {
  if (!supabase) {
    return () => {};
  }

  const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
    callback(session);
  });

  return () => {
    subscription.unsubscribe();
  };
}
