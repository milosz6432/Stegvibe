import * as React from 'react'

import { cn } from '@/lib/utils'

export function Table({ className, ...props }: React.ComponentProps<'table'>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn('w-full border-collapse text-[13px]', className)} {...props} />
    </div>
  )
}
export const THead = (p: React.ComponentProps<'thead'>) => <thead {...p} />
export const TBody = (p: React.ComponentProps<'tbody'>) => <tbody {...p} />
export function TR({ className, ...props }: React.ComponentProps<'tr'>) {
  return <tr className={cn('border-b last:border-0 hover:bg-accent/40', className)} {...props} />
}
export function TH({ className, ...props }: React.ComponentProps<'th'>) {
  return <th className={cn('label-caps border-b px-3 py-1.5 text-left font-semibold', className)} {...props} />
}
export function TD({ className, ...props }: React.ComponentProps<'td'>) {
  return <td className={cn('px-3 py-1.5 align-middle', className)} {...props} />
}
