import { SignInButton, SignedIn, SignedOut, UserButton, useClerk, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import Head from "next/head";
import { useCallback, useEffect } from "react";
import { useRouter } from "next/router";
import { API_URL } from "../lib/config";
import { showToast } from "../components/Toast";

export default function Home() {
  const router = useRouter();
  const { isSignedIn } = useAuth();
  const { openSignUp, signOut } = useClerk();

  const handleSignupClick = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/signup-allowance`);
      if (resp.ok) {
        const data = await resp.json();
        const remaining = Number(data.remaining || 0);
        const tryAfter = String(data.try_after || "00:00");
        if (remaining <= 0) {
          const [hh, mm] = tryAfter.split(":");
          showToast('error', `Signups are full today. Please try after ${hh} hours and ${mm} minutes.`, 0);
          return;
        }
      }
    } catch { }
    openSignUp();
  }, [openSignUp]);

  useEffect(() => {
    const run = async () => {
      if (!router.isReady) return;
      const flag = router.query.signupCheck === '1';
      if (!flag || !isSignedIn) return;
      try {
        const resp = await fetch(`${API_URL}/api/signup-allowance`);
        if (resp.ok) {
          const data = await resp.json();
          const remaining = Number(data.remaining || 0);
          const tryAfter = String(data.try_after || "00:00");
          if (remaining <= 0) {
            const [hh, mm] = tryAfter.split(":");
            showToast('error', `Signups are full today. Please try after ${hh} hours and ${mm} minutes.`, 0);
            await signOut();
            router.replace('/', undefined, { shallow: true });
          }
        }
      } catch { }
    };
    run();
  }, [router, isSignedIn, signOut]);
  return (
    <>
      <Head>
        <title>Alex AI Financial Advisor - Intelligent Portfolio Management</title>
      </Head>
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-gray-50">
        {/* Navigation */}
        <nav className="px-8 py-6 bg-white shadow-sm">
          <div className="max-w-7xl mx-auto flex justify-between items-center">
            <div className="text-2xl font-bold text-dark">
              Alex <span className="text-primary">AI Financial Advisor</span>
            </div>
            <div className="flex gap-4">
              <SignedOut>
                <SignInButton mode="modal" signUpForceRedirectUrl="/?signupCheck=1" signUpFallbackRedirectUrl="/?signupCheck=1">
                  <button className="px-6 py-2 text-primary border border-primary rounded-lg hover:bg-primary hover:text-white transition-colors">
                    Sign In
                  </button>
                </SignInButton>
                <button onClick={handleSignupClick} className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-blue-600 transition-colors">
                  Get Started
                </button>
              </SignedOut>
              <SignedIn>
                <div className="flex items-center gap-4">
                  <Link href="/dashboard">
                    <button className="px-6 py-2 bg-ai-accent text-white rounded-lg hover:bg-purple-700 transition-colors">
                      Go to Dashboard
                    </button>
                  </Link>
                  <UserButton afterSignOutUrl="/" />
                </div>
              </SignedIn>
            </div>
          </div>
        </nav>

        {/* Hero Section */}
        <section className="px-8 py-20">
          <div className="max-w-7xl mx-auto text-center">
            <h1 className="text-5xl font-bold text-dark mb-6">
              Your AI-Powered Financial Future
            </h1>
            <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto">
              Experience the power of autonomous AI agents working together to analyze your portfolio,
              plan your retirement, and optimize your investments.
            </p>
            <div className="flex gap-6 justify-center">
              <SignedOut>
                <button onClick={handleSignupClick} className="px-8 py-4 bg-ai-accent text-white text-lg rounded-lg hover:bg-purple-700 transition-colors shadow-lg">
                  Start Your Analysis
                </button>
              </SignedOut>
              <SignedIn>
                <Link href="/dashboard">
                  <button className="px-8 py-4 bg-ai-accent text-white text-lg rounded-lg hover:bg-purple-700 transition-colors shadow-lg">
                    Open Dashboard
                  </button>
                </Link>
              </SignedIn>
              <button className="px-8 py-4 border-2 border-primary text-primary text-lg rounded-lg hover:bg-primary hover:text-white transition-colors">
                Watch Demo
              </button>
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section className="px-8 py-20 bg-white">
          <div className="max-w-7xl mx-auto">
            <h2 className="text-3xl font-bold text-center text-dark mb-12">
              Meet Your AI Advisory Team
            </h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
              <div className="text-center p-6 rounded-xl hover:shadow-lg transition-shadow">
                <div className="text-4xl mb-4">🎯</div>
                <h3 className="text-xl font-semibold text-ai-accent mb-2">Financial Planner</h3>
                <p className="text-gray-600">Coordinates your complete financial analysis with intelligent orchestration</p>
              </div>
              <div className="text-center p-6 rounded-xl hover:shadow-lg transition-shadow">
                <div className="text-4xl mb-4">📊</div>
                <h3 className="text-xl font-semibold text-primary mb-2">Portfolio Analyst</h3>
                <p className="text-gray-600">Deep analysis of holdings, performance metrics, and risk assessment</p>
              </div>
              <div className="text-center p-6 rounded-xl hover:shadow-lg transition-shadow">
                <div className="text-4xl mb-4">📈</div>
                <h3 className="text-xl font-semibold text-success mb-2">Chart Specialist</h3>
                <p className="text-gray-600">Visualizes your portfolio composition with interactive charts</p>
              </div>
              <div className="text-center p-6 rounded-xl hover:shadow-lg transition-shadow">
                <div className="text-4xl mb-4">🎯</div>
                <h3 className="text-xl font-semibold text-accent mb-2">Retirement Planner</h3>
                <p className="text-gray-600">Projects your retirement readiness with Monte Carlo simulations</p>
              </div>
            </div>
          </div>
        </section>

        {/* Benefits Section */}
        <section className="px-8 py-20 bg-gradient-to-r from-primary/10 to-ai-accent/10">
          <div className="max-w-7xl mx-auto">
            <h2 className="text-3xl font-bold text-center text-dark mb-12">
              Enterprise-Grade AI Advisory
            </h2>
            <div className="grid md:grid-cols-3 gap-8">
              <div className="bg-white p-8 rounded-xl shadow-md">
                <div className="text-accent text-2xl mb-4">⚡</div>
                <h3 className="text-xl font-semibold mb-3">Real-Time Analysis</h3>
                <p className="text-gray-600">Watch AI agents collaborate in parallel to analyze your complete financial picture</p>
              </div>
              <div className="bg-white p-8 rounded-xl shadow-md">
                <div className="text-accent text-2xl mb-4">🔒</div>
                <h3 className="text-xl font-semibold mb-3">Bank-Level Security</h3>
                <p className="text-gray-600">Your data is protected with enterprise security and row-level access controls</p>
              </div>
              <div className="bg-white p-8 rounded-xl shadow-md">
                <div className="text-accent text-2xl mb-4">📊</div>
                <h3 className="text-xl font-semibold mb-3">Comprehensive Reports</h3>
                <p className="text-gray-600">Detailed markdown reports with interactive charts and retirement projections</p>
              </div>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="px-8 py-20 bg-dark text-white">
          <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-3xl font-bold mb-6">
              Ready to Transform Your Financial Future?
            </h2>
            <p className="text-xl mb-8 opacity-90">
              Join thousands of investors using AI to optimize their portfolios
            </p>
            <button onClick={handleSignupClick} className="px-8 py-4 bg-accent text-dark font-semibold text-lg rounded-lg hover:bg-yellow-500 transition-colors shadow-lg">
              Get Started Free
            </button>
          </div>
        </section>

        {/* Footer */}
        <footer className="px-8 py-6 bg-gray-900 text-gray-400 text-center text-sm">
          <p>© 2025 Alex AI Financial Advisor. All rights reserved.</p>
          <p className="mt-2">
            This AI-generated advice has not been vetted by a qualified financial advisor and should not be used for trading decisions.
            For informational purposes only.
          </p>
        </footer>
      </div>
    </>
  );
}