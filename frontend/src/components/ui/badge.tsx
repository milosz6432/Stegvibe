import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-[11px] font-medium leading-4 whitespace-nowrap',
  {
    variants: {
      variant: {
        default: 'border-border bg-secondary text-secondary-foreground',
        outline: 'border-border bg-transparent text-muted-foreground',
        primary: 'border-primary/30 bg-primary/10 text-primary',
        ok: 'border-ok/30 bg-ok/10 text-ok',
        warn: 'border-warn/30 bg-warn/10 text-warn',
        danger: 'border-destructive/40 bg-destructive/10 text-destructive',
        info: 'border-info/30 bg-info/10 text-info',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps extends React.ComponentProps<'span'>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
