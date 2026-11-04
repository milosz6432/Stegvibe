import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { JsonSchema } from '@/api/types'
import { defaultsFromSchema, propertyType, SchemaForm } from '@/components/SchemaForm'

// The real schema published by the backend for core.integrity_verify
const INTEGRITY: JsonSchema = {
  type: 'object',
  properties: {
    chunk_size_kib: { type: 'integer', default: 1024, minimum: 4, maximum: 65536, description: 'Read buffer size in KiB', title: 'Chunk Size Kib' },
  },
}

describe('defaultsFromSchema / propertyType', () => {
  it('collects declared defaults only', () => {
    expect(defaultsFromSchema(INTEGRITY)).toEqual({ chunk_size_kib: 1024 })
    expect(defaultsFromSchema({ type: 'object', properties: { a: { type: 'string' } } })).toEqual({})
  })
  it('looks through nullable unions', () => {
    expect(propertyType({ anyOf: [{ type: 'null' }, { type: 'integer' }] })).toBe('integer')
    expect(propertyType({ type: ['null', 'number'] })).toBe('number')
  })
})

describe('<SchemaForm>', () => {
  it('says so when a plugin has no options', () => {
    render(<SchemaForm schema={{ type: 'object', properties: {} }} value={{}} onChange={() => {}} />)
    expect(screen.getByText(/no configurable options/i)).toBeInTheDocument()
  })

  it('renders bounds from the schema and propagates numeric edits', async () => {
    const onChange = vi.fn()
    function Harness() {
      const [v, setV] = useState<Record<string, unknown>>(defaultsFromSchema(INTEGRITY))
      return <SchemaForm schema={INTEGRITY} value={v} onChange={(n) => { setV(n); onChange(n) }} />
    }
    render(<Harness />)
    const input = screen.getByLabelText(/chunk size kib/i) as HTMLInputElement
    expect(input).toHaveAttribute('min', '4')
    expect(input).toHaveAttribute('max', '65536')
    expect(input.value).toBe('1024')
    expect(screen.getByText('Read buffer size in KiB')).toBeInTheDocument()

    await userEvent.clear(input)
    expect(onChange).toHaveBeenLastCalledWith({}) // cleared => key removed, server default applies
    await userEvent.type(input, '64')
    expect(onChange).toHaveBeenLastCalledWith({ chunk_size_kib: 64 })
  })

  it('supports booleans and enums', async () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: { flag: { type: 'boolean', default: false }, order: { type: 'string', enum: ['msb', 'lsb'], default: 'msb' } },
    }
    const onChange = vi.fn()
    render(<SchemaForm schema={schema} value={{ flag: false, order: 'msb' }} onChange={onChange} />)
    await userEvent.click(screen.getByLabelText('flag'))
    expect(onChange).toHaveBeenLastCalledWith({ flag: true, order: 'msb' })
    await userEvent.selectOptions(screen.getByLabelText('order'), 'lsb')
    expect(onChange).toHaveBeenLastCalledWith({ flag: false, order: 'lsb' })
  })
})
