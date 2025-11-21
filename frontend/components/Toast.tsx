import { useEffect, useState } from 'react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
  duration?: number;
}

interface ToastProps {
  toast: ToastMessage;
  onClose: (id: string) => void;
}

const Toast = ({ toast, onClose }: ToastProps) => {
  useEffect(() => {
    if (toast.duration === 0) {
      return;
    }

    const timer = setTimeout(() => {
      onClose(toast.id);
    }, toast.duration ?? 3000);

    return () => clearTimeout(timer);
  }, [toast, onClose]);

  const bgColor = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    info: 'bg-blue-500'
  }[toast.type];

  const icon = {
    success: '✓',
    error: '⚠️',
    info: 'ℹ'
  }[toast.type];

  return (
    <div className={`${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-slide-in`}>
      <span className="text-xl">{icon}</span>
      <p className="flex-1">{toast.message}</p>
      <button
        onClick={() => onClose(toast.id)}
        aria-label="Close notification"
        className="ml-1 w-6 h-6 flex items-center justify-center rounded-full border border-white/70 bg-white/10 hover:bg-white/20 transition-colors"
      >
        <span className="text-sm leading-none">✕</span>
      </button>
    </div>
  );
};

export const ToastContainer = () => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const handleToast = (event: CustomEvent<Omit<ToastMessage, 'id'>>) => {
      const newToast: ToastMessage = {
        ...event.detail,
        id: Date.now().toString()
      };
      setToasts(prev => [...prev, newToast]);
    };

    window.addEventListener('toast', handleToast as EventListener);
    return () => window.removeEventListener('toast', handleToast as EventListener);
  }, []);

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {toasts.map(toast => (
        <Toast key={toast.id} toast={toast} onClose={removeToast} />
      ))}
    </div>
  );
};

// Helper function to show toast
export const showToast = (type: 'success' | 'error' | 'info', message: string, duration?: number) => {
  window.dispatchEvent(new CustomEvent('toast', {
    detail: { type, message, duration }
  }));
};