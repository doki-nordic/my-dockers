const fs = require('fs');
const path = require('path');
const esbuild = require('esbuild');
const copyStaticFiles = require('esbuild-copy-static-files');

build({
    entryPoints: ['temp/index.jsx'],
    bundle: true,
    sourcemap: true,
    minify: true,
    format: 'iife',
    outdir: path.join(__dirname, '../dist'),
    metafile: false,
    loader: {
        '.ttf': 'file',
        '.svg': 'file',
        '.woff': 'file',
        '.woff2': 'file',
        '.eot': 'file',
    },
    plugins: [
        copyStaticFiles({
            src: 'static',
            dest: 'dist',
            dereference: true,
            errorOnExist: false,
            recursive: true,
        })
    ],
}, true);


async function build(opts, startServer, metaFileName) {
    let mode = (process.argv[2] || '').substring(0, 1).toLowerCase();
    let ctx = await esbuild.context(opts);
    if (startServer && mode === 's') {
        let result = await ctx.serve({
            host: '127.0.0.1',
            port: 8080,
            servedir: path.join(__dirname, '../dist'),
        });
        console.log('Server running on:');
        console.log(`    http://${result.host}:${result.port}/`);
    } else if (mode !== '') {
        await ctx.watch();
    } else {
        let result = await ctx.rebuild();
        if (result.errors.length > 0) {
            console.error(result.errors);
        }
        if (result.warnings.length > 0) {
            console.error(result.warnings);
        }
        if (!result.errors.length && !result.warnings.length) {
            console.log('Build done.');
        }
        ctx.dispose();
        if (!mode && metaFileName && result.metafile) {
            fs.mkdirSync(path.dirname(metaFileName), { recursive: true });
            fs.writeFileSync(metaFileName, JSON.stringify(result.metafile, null, 4));
        }
    }
}