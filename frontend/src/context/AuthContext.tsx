import React, { useState, useEffect, useCallback, ReactNode } from 'react';
import { AuthUser } from '../types';
import {
  isSupabaseConfigured,
  getSupabaseSession,
  onSupabaseAuthStateChange,
  signInWithEmail as sbSignInWithEmail,
  signUpWithEmail as sbSignUpWithEmail,
  signOutUser as sbSignOutUser,
} from '../services/supabaseClient';
import {
  setCurrentUser,
  DEMO_USERS,
  subscribeToUserChanges,
  getSessionToken,
} from '../services/dataService';
import { AuthContext } from './authContextDef';

const DEMO_SESSION_KEY = 'restockiq_explicit_demo_session';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const isConfigured = isSupabaseConfigured();
  const [user, setUser] = useState<AuthUser | null>(() => {
    // If not configured, default to planner demo
    if (!isConfigured) return DEMO_USERS[0];
    // In production with Supabase, demo identities are strictly disabled to prevent 401s on protected APIs
    if (import.meta.env.PROD) {
      localStorage.removeItem(DEMO_SESSION_KEY);
      return null;
    }
    // If configured in non-production, check if explicit demo session was stored
    const savedDemo = localStorage.getItem(DEMO_SESSION_KEY);
    if (savedDemo) {
      try {
        const parsed = JSON.parse(savedDemo);
        return parsed;
      } catch {
        return null;
      }
    }
    return null;
  });

  const [sessionToken, setSessionToken] = useState<string | null>(() => getSessionToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Sync with dataService
  useEffect(() => {
    const unsubscribe = subscribeToUserChanges((newUser, newToken) => {
      setUser(newUser);
      setSessionToken(newToken);
    });
    return unsubscribe;
  }, []);

  // Initialize session restoration on mount
  useEffect(() => {
    let mounted = true;

    async function initSession() {
      if (!isConfigured) {
        // Offline / dev mode without Supabase keys
        const defaultUser = DEMO_USERS[0];
        setCurrentUser(defaultUser);
        if (mounted) {
          setUser(defaultUser);
          setIsLoading(false);
        }
        return;
      }

      try {
        const session = await getSupabaseSession();
        if (!mounted) return;

        if (session && session.user) {
          const u = session.user;
          const role =
            (u.app_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
            (u.user_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
            'planner';
          const authUser: AuthUser = {
            id: u.id,
            email: u.email || '',
            name: (u.user_metadata?.name as string) || u.email || 'Supabase User',
            role,
            is_demo: false,
          };
          localStorage.removeItem(DEMO_SESSION_KEY);
          setCurrentUser(authUser);
          setUser(authUser);
          setSessionToken(session.access_token);
        } else {
          // In production with Supabase, demo identities cannot authenticate against the production backend
          if (import.meta.env.PROD) {
            localStorage.removeItem(DEMO_SESSION_KEY);
            setUser(null);
            setSessionToken(null);
          } else {
            // Check if explicit demo persona was selected previously in local development
            const savedDemo = localStorage.getItem(DEMO_SESSION_KEY);
            if (savedDemo) {
              try {
                const parsed = JSON.parse(savedDemo);
                setCurrentUser(parsed);
                setUser(parsed);
                setSessionToken(null);
              } catch {
                setUser(null);
                setSessionToken(null);
              }
            } else {
              setUser(null);
              setSessionToken(null);
            }
          }
        }
      } catch (err) {
        console.warn('Session restoration notice:', err);
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    initSession();

    // Listen to Supabase auth state changes
    const cleanupAuth = onSupabaseAuthStateChange((session) => {
      if (!mounted) return;
      if (session && session.user) {
        const u = session.user;
        const role =
          (u.app_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
          (u.user_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
          'planner';
        const authUser: AuthUser = {
          id: u.id,
          email: u.email || '',
          name: (u.user_metadata?.name as string) || u.email || 'Supabase User',
          role,
          is_demo: false,
        };
        localStorage.removeItem(DEMO_SESSION_KEY);
        setCurrentUser(authUser);
        setUser(authUser);
        setSessionToken(session.access_token);
      } else {
        setUser((prev) => {
          if (prev && !prev.is_demo) {
            setSessionToken(null);
            return null;
          }
          return prev;
        });
      }
    });

    return () => {
      mounted = false;
      cleanupAuth();
    };
  }, [isConfigured]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
      setIsLoading(true);
      try {
        const res = await sbSignInWithEmail(email, password);
        if (res.error) {
          setIsLoading(false);
          return { success: false, error: res.error };
        }

        if (res.user) {
          const role =
            (res.user.app_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
            (res.user.user_metadata?.role as 'planner' | 'approver' | 'auditor' | 'admin') ||
            'planner';
          const newUser: AuthUser = {
            id: res.user.id,
            email: res.user.email || email,
            name: (res.user.user_metadata?.name as string) || res.user.email || 'Supabase User',
            role,
            is_demo: false,
          };
          localStorage.removeItem(DEMO_SESSION_KEY);
          setCurrentUser(newUser);
          setUser(newUser);
          setSessionToken(res.session?.access_token || null);
          setIsLoading(false);
          return { success: true };
        }

        setIsLoading(false);
        return { success: false, error: 'Authentication returned no user record.' };
      } catch (err) {
        setIsLoading(false);
        const msg = err instanceof Error ? err.message : 'Sign in failed.';
        return { success: false, error: msg };
      }
    },
    []
  );

  const signUp = useCallback(
    async (
      email: string,
      password: string
    ): Promise<{ success: boolean; error?: string; sessionCreated?: boolean }> => {
      setIsLoading(true);
      try {
        const res = await sbSignUpWithEmail(email, password);
        setIsLoading(false);
        if (res.error) {
          return { success: false, error: res.error };
        }

        // If session created immediately (e.g. email confirmation disabled in Supabase)
        if (res.session && res.user) {
          const newUser: AuthUser = {
            id: res.user.id,
            email: res.user.email || email,
            name: (res.user.user_metadata?.name as string) || res.user.email || 'Supabase User',
            role: 'planner',
            is_demo: false,
          };
          localStorage.removeItem(DEMO_SESSION_KEY);
          setCurrentUser(newUser);
          setUser(newUser);
          setSessionToken(res.session.access_token);
          return { success: true, sessionCreated: true };
        }

        return { success: true, sessionCreated: false };
      } catch (err) {
        setIsLoading(false);
        const msg = err instanceof Error ? err.message : 'Registration failed.';
        return { success: false, error: msg };
      }
    },
    []
  );

  const signOut = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      localStorage.removeItem(DEMO_SESSION_KEY);
      await sbSignOutUser();
    } finally {
      if (isConfigured) {
        setUser(null);
        setSessionToken(null);
      } else {
        const fallback = DEMO_USERS[0];
        setCurrentUser(fallback);
        setUser(fallback);
        setSessionToken(null);
      }
      setIsLoading(false);
    }
  }, [isConfigured]);

  const selectDemoUser = useCallback(
    (demoUser: AuthUser): void => {
      if (import.meta.env.PROD && isConfigured) {
        console.warn('Demo persona selection is disabled in production mode with Supabase.');
        return;
      }
      localStorage.setItem(DEMO_SESSION_KEY, JSON.stringify(demoUser));
      setCurrentUser(demoUser);
      setUser(demoUser);
      setSessionToken(null);
    },
    [isConfigured]
  );

  const toggleDemoRole = useCallback((): void => {
    if (import.meta.env.PROD && isConfigured) {
      return;
    }
    const current = user || DEMO_USERS[0];
    const nextUser = current.role === 'planner' ? DEMO_USERS[1] : DEMO_USERS[0];
    selectDemoUser(nextUser);
  }, [user, selectDemoUser, isConfigured]);

  const isAuthenticated = Boolean(user !== null);

  return (
    <AuthContext.Provider
      value={{
        user,
        sessionToken,
        isAuthenticated,
        isLoading,
        isConfigured,
        signIn,
        signUp,
        signOut,
        selectDemoUser,
        toggleDemoRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

