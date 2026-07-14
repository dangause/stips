import * as esbuild from 'esbuild'
import {argv} from 'node:process'

await esbuild.build({
  entryPoints: [argv[2]],
  bundle: true,
  drop:  ["console"],
  outfile: argv[3],
})
