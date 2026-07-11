import * as esbuild from 'esbuild'
import {argv} from 'node:process'

await esbuild.build({
  entryPoints: [argv[2]],
  bundle: true,
  outfile: argv[3],
})
