"""
Infraestrutura do site ticketcar.com.br (idempotente: pode rodar de novo).

  S3        ticketcar-site-<conta> (sa-east-1), privado, criptografado; só o CloudFront lê (OAC)
  ACM       certificado us-east-1 para ticketcar.com.br e www (validado por DNS no Cloudflare)
  CloudFront distribuição com os dois domínios, HTTPS, cabeçalhos de segurança, www → sem www,
            /pasta/ → /pasta/index.html e 404 bonito
  Cloudflare ticketcar.com.br e www → CloudFront (só DNS, nuvem cinza). Troca o site padrão do GoDaddy.
            Não mexe em MX/TXT (e-mail).

Roda com boto3 (Python), com credenciais temporárias em ../.aws-temp.env e o token do Cloudflare
(permissão "Edit zone DNS") em ../token-cloudflare-dns.txt. Grava o resultado em site-infra.json.

  python scripts/infra.py            cria/atualiza a infraestrutura
  python scripts/infra.py --publish  também gera o site (node build.mjs) e publica dist/
"""
import json, mimetypes, os, subprocess, sys, time, urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]          # ticket-car-site/
WORKSPACE = ROOT.parent                              # TicketCar/
DOMAIN = 'ticketcar.com.br'
NAMES = [DOMAIN, f'www.{DOMAIN}']
REGION = 'sa-east-1'
TAGS = {'project': 'ticketcar', 'env': 'prd', 'purpose': 'site'}
STATE = ROOT / 'site-infra.json'
CACHING_OPTIMIZED = '658327ea-f89d-4fab-a63d-7e88639e58f6'
SECURITY_HEADERS = '67f7725c-6f97-4210-82d7-5512b31e9d03'


def load_creds():
    for line in (WORKSPACE / '.aws-temp.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k.strip().removeprefix('export ').strip()] = v.strip().strip('"').strip("'")


def cf_token():
    for n in ['token-cloudflare-dns.txt', 'token-cloudflare-dns.txt.txt']:
        p = WORKSPACE / n
        if not p.exists():
            continue
        lines = [l.strip() for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
        for i, l in enumerate(lines):  # arquivo copiado do painel: o token vem na linha depois do rótulo
            if l.lower() in ('your api token', 'seu token de api') and i + 1 < len(lines):
                return lines[i + 1]
        if len(lines) == 1:
            return lines[0]
    sys.exit('Token do Cloudflare não encontrado (token-cloudflare-dns.txt).')


class Cloudflare:
    def __init__(self, token):
        self.token = token
        self.zone = self.call('GET', f'/zones?name={DOMAIN}')[0]['id']

    def call(self, method, path, body=None):
        req = urllib.request.Request(f'https://api.cloudflare.com/client/v4{path}', method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        if not data.get('success'):
            raise RuntimeError(f'Cloudflare: {data.get("errors")}')
        return data['result']

    def records(self, name):
        return self.call('GET', f'/zones/{self.zone}/dns_records?name={name}&per_page=100')

    def upsert(self, type_, name, content, proxied=False, priority=None, replace_types=None):
        """Garante UM registro type_/name com esse conteúdo. replace_types: tipos que conflitam e são removidos."""
        body = {'type': type_, 'name': name, 'content': content, 'ttl': 1, 'proxied': proxied}
        if priority is not None:
            body['priority'] = priority
        same = [r for r in self.records(name) if r['type'] == type_]
        for r in self.records(name):
            if replace_types and r['type'] in replace_types and r['type'] != type_:
                self.call('DELETE', f'/zones/{self.zone}/dns_records/{r["id"]}')
                print(f'  DNS removido: {r["type"]} {name} → {r["content"]}')
        if same:
            if same[0]['content'].rstrip('.') == content.rstrip('.') and same[0].get('proxied', False) == proxied:
                return print(f'  DNS ok: {type_} {name}')
            self.call('PUT', f'/zones/{self.zone}/dns_records/{same[0]["id"]}', body)
            for extra in same[1:]:
                self.call('DELETE', f'/zones/{self.zone}/dns_records/{extra["id"]}')
            return print(f'  DNS atualizado: {type_} {name} → {content}')
        self.call('POST', f'/zones/{self.zone}/dns_records', body)
        print(f'  DNS criado: {type_} {name} → {content}')


def ensure_bucket(s3, bucket):
    try:
        s3.head_bucket(Bucket=bucket)
        print(f'  bucket já existe: {bucket}')
    except ClientError:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={'LocationConstraint': REGION})
        print(f'  bucket criado: {bucket}')
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={k: True for k in ['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets']})
    s3.put_bucket_ownership_controls(Bucket=bucket, OwnershipControls={'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}, 'BucketKeyEnabled': True}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={'TagSet': [{'Key': k, 'Value': v} for k, v in TAGS.items()]})


def ensure_cert(acm, cf):
    certs = acm.list_certificates(CertificateStatuses=['ISSUED', 'PENDING_VALIDATION'])['CertificateSummaryList']
    arn = next((c['CertificateArn'] for c in certs if c['DomainName'] == DOMAIN), None)
    if not arn:
        arn = acm.request_certificate(DomainName=DOMAIN, SubjectAlternativeNames=NAMES[1:], ValidationMethod='DNS', IdempotencyToken='ticketcarsite',
                                      Tags=[{'Key': k, 'Value': v} for k, v in TAGS.items()])['CertificateArn']
        print('  certificado pedido')
    for _ in range(14):  # ~140 s por execução; se não emitiu, rode de novo
        c = acm.describe_certificate(CertificateArn=arn)['Certificate']
        opts = c.get('DomainValidationOptions', [])
        if c['Status'] == 'ISSUED':
            print('  certificado emitido')
            return arn
        rrs = [o['ResourceRecord'] for o in opts if 'ResourceRecord' in o]
        if len(rrs) == len(NAMES):
            for rr in {r['Name']: r for r in rrs}.values():
                cf.upsert('CNAME', rr['Name'].rstrip('.'), rr['Value'].rstrip('.'))
        time.sleep(10)
    sys.exit('Certificado ainda não emitido; rode de novo em alguns minutos.')


FUNCTION_CODE = f"""function handler(event) {{
  var req = event.request;
  var host = req.headers.host ? req.headers.host.value : '';
  if (host === 'www.{DOMAIN}') {{
    var qs = req.querystring && Object.keys(req.querystring).length ? '?' + Object.keys(req.querystring).map(function (k) {{ return k + '=' + req.querystring[k].value; }}).join('&') : '';
    return {{ statusCode: 301, statusDescription: 'Moved Permanently', headers: {{ location: {{ value: 'https://{DOMAIN}' + req.uri + qs }} }} }};
  }}
  if (req.uri.endsWith('/')) req.uri += 'index.html';
  else if (req.uri.lastIndexOf('.') < req.uri.lastIndexOf('/')) req.uri += '/index.html';
  return req;
}}"""


def ensure_function(cfr):
    name = 'ticketcar-site-router'
    try:
        etag = cfr.describe_function(Name=name, Stage='DEVELOPMENT')['ETag']
        etag = cfr.update_function(Name=name, IfMatch=etag, FunctionConfig={'Comment': 'www->apex e index.html', 'Runtime': 'cloudfront-js-2.0'}, FunctionCode=FUNCTION_CODE.encode())['ETag']
    except cfr.exceptions.NoSuchFunctionExists:
        etag = cfr.create_function(Name=name, FunctionConfig={'Comment': 'www->apex e index.html', 'Runtime': 'cloudfront-js-2.0'}, FunctionCode=FUNCTION_CODE.encode())['ETag']
    return cfr.publish_function(Name=name, IfMatch=etag)['FunctionSummary']['FunctionMetadata']['FunctionARN']


def ensure_oac(cfr, bucket):
    name = f'{bucket}-oac'
    for o in cfr.list_origin_access_controls().get('OriginAccessControlList', {}).get('Items', []):
        if o['Name'] == name:
            return o['Id']
    return cfr.create_origin_access_control(OriginAccessControlConfig={'Name': name, 'SigningProtocol': 'sigv4', 'SigningBehavior': 'always', 'OriginAccessControlOriginType': 's3'})['OriginAccessControl']['Id']


def ensure_distribution(cfr, bucket, cert, fn_arn, oac):
    for d in cfr.list_distributions().get('DistributionList', {}).get('Items', []):
        if DOMAIN in d.get('Aliases', {}).get('Items', []):
            print(f'  CloudFront já existe: {d["Id"]}')
            return d['Id'], d['DomainName'], d['ARN']
    origin = f'{bucket}.s3.{REGION}.amazonaws.com'
    cfg = {
        'CallerReference': 'ticketcar-site',
        'Comment': 'ticketcar.com.br (site institucional)',
        'Enabled': True,
        'Aliases': {'Quantity': len(NAMES), 'Items': NAMES},
        'DefaultRootObject': 'index.html',
        'HttpVersion': 'http2and3',
        'PriceClass': 'PriceClass_All',
        'IsIPV6Enabled': True,
        'Origins': {'Quantity': 1, 'Items': [{'Id': 's3-site', 'DomainName': origin, 'OriginAccessControlId': oac, 'S3OriginConfig': {'OriginAccessIdentity': ''}}]},
        'DefaultCacheBehavior': {
            'TargetOriginId': 's3-site', 'ViewerProtocolPolicy': 'redirect-to-https', 'Compress': True,
            'CachePolicyId': CACHING_OPTIMIZED, 'ResponseHeadersPolicyId': SECURITY_HEADERS,
            'AllowedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD'], 'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']}},
            'FunctionAssociations': {'Quantity': 1, 'Items': [{'FunctionARN': fn_arn, 'EventType': 'viewer-request'}]},
        },
        'CustomErrorResponses': {'Quantity': 2, 'Items': [
            {'ErrorCode': 403, 'ResponsePagePath': '/404.html', 'ResponseCode': '404', 'ErrorCachingMinTTL': 60},
            {'ErrorCode': 404, 'ResponsePagePath': '/404.html', 'ResponseCode': '404', 'ErrorCachingMinTTL': 60},
        ]},
        'ViewerCertificate': {'ACMCertificateArn': cert, 'SSLSupportMethod': 'sni-only', 'MinimumProtocolVersion': 'TLSv1.2_2021'},
    }
    d = cfr.create_distribution_with_tags(DistributionConfigWithTags={'DistributionConfig': cfg, 'Tags': {'Items': [{'Key': k, 'Value': v} for k, v in TAGS.items()]}})['Distribution']
    print(f'  CloudFront criado: {d["Id"]}')
    return d['Id'], d['DomainName'], d['ARN']


def bucket_policy(s3, bucket, dist_arn):
    policy = {'Version': '2012-10-17', 'Statement': [
        {'Sid': 'CloudFrontLe', 'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'}, 'Action': 's3:GetObject',
         'Resource': f'arn:aws:s3:::{bucket}/*', 'Condition': {'StringEquals': {'AWS:SourceArn': dist_arn}}},
        {'Sid': 'SomenteHttps', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*', 'Resource': [f'arn:aws:s3:::{bucket}', f'arn:aws:s3:::{bucket}/*'],
         'Condition': {'Bool': {'aws:SecureTransport': 'false'}}},
    ]}
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))


def publish(s3, cfr, bucket, dist_id):
    subprocess.run(['node', 'build.mjs'], cwd=ROOT, check=True)
    dist = ROOT / 'dist'
    keep = set()
    for f in dist.rglob('*'):
        if f.is_dir():
            continue
        key = f.relative_to(dist).as_posix()
        keep.add(key)
        ctype = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
                 '.svg': 'image/svg+xml', '.xml': 'application/xml', '.txt': 'text/plain; charset=utf-8'}.get(f.suffix) or mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
        cache = 'public, max-age=300' if f.suffix in ('.html', '.xml', '.txt') else 'public, max-age=86400'
        s3.upload_file(str(f), bucket, key, ExtraArgs={'ContentType': ctype, 'CacheControl': cache})
    print(f'  {len(keep)} arquivos publicados')
    cfr.create_invalidation(DistributionId=dist_id, InvalidationBatch={'Paths': {'Quantity': 1, 'Items': ['/*']}, 'CallerReference': str(time.time())})
    print('  cache do CloudFront limpo')


def main():
    load_creds()
    acct = boto3.client('sts').get_caller_identity()['Account']
    bucket = f'ticketcar-site-{acct}'
    s3 = boto3.client('s3', region_name=REGION)
    cfr = boto3.client('cloudfront')
    acm = boto3.client('acm', region_name='us-east-1')
    cf = Cloudflare(cf_token())

    print('== S3'); ensure_bucket(s3, bucket)
    print('== Certificado'); cert = ensure_cert(acm, cf)
    print('== CloudFront')
    fn = ensure_function(cfr)
    oac = ensure_oac(cfr, bucket)
    dist_id, dist_domain, dist_arn = ensure_distribution(cfr, bucket, cert, fn, oac)
    bucket_policy(s3, bucket, dist_arn)
    print('== DNS (Cloudflare)')
    for name in NAMES:
        cf.upsert('CNAME', name, dist_domain, replace_types={'A', 'AAAA', 'CNAME'})
    STATE.write_text(json.dumps({'bucket': bucket, 'distributionId': dist_id, 'cloudfront': dist_domain, 'certificate': cert, 'urls': [f'https://{n}' for n in NAMES]}, indent=1))
    if '--publish' in sys.argv:
        print('== Publicação'); publish(s3, cfr, bucket, dist_id)
    print('PRONTO:', ', '.join(f'https://{n}' for n in NAMES))


if __name__ == '__main__':
    main()
