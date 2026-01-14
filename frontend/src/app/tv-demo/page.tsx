/**
 * TV Components - Redirect to Dashboard
 * Components are ready, will be wired to real data on dashboard/strategy pages
 */
import { redirect } from 'next/navigation';

export default function TVDemoPage() {
  redirect('/dashboard');
}
