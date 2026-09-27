"""
Papel IAM do GitHub Actions para publicar o site (OIDC, sem chave guardada no GitHub). Idempotente.

  ticketcar-gh-site-prd
    confiança: só o repositório luanromeu/ticket-car-site, só a branch main
               (aceita o formato antigo e o novo do "sub", como os papéis dos outros repositórios)
    pode:      listar/gravar/apagar no bucket do site e invalidar o cache da distribuição dele

Roda com boto3 e as credenciais temporárias em ../../.aws-temp.env:  python scripts/ci_role.py
"""
import json, os
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_OWNER_ID = '38258641'  # id imutável da conta GitHub luanromeu
REPO = 'ticket-car-site'
ROLE = 'ticketcar-gh-site-prd'


def load_creds():
    for line in (ROOT.parent / '.aws-temp.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k.strip().removeprefix('export ').strip()] = v.strip().strip('"').strip("'")


def main():
    load_creds()
    state = json.loads((ROOT / 'site-infra.json').read_text())
    acct = boto3.client('sts').get_caller_identity()['Account']
    iam = boto3.client('iam')
    provider = f'arn:aws:iam::{acct}:oidc-provider/token.actions.githubusercontent.com'
    trust = {'Version': '2012-10-17', 'Statement': [{
        'Effect': 'Allow', 'Principal': {'Federated': provider}, 'Action': 'sts:AssumeRoleWithWebIdentity',
        'Condition': {
            'StringEquals': {'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com'},
            'StringLike': {'token.actions.githubusercontent.com:sub': [
                f'repo:luanromeu/{REPO}:ref:refs/heads/main',
                f'repo:luanromeu@{ACCOUNT_OWNER_ID}/{REPO}@*:ref:refs/heads/main',
            ]},
        }}]}
    try:
        iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust), Description='GitHub Actions: publica o site ticketcar.com.br (main)',
                        MaxSessionDuration=3600, Tags=[{'Key': 'project', 'Value': 'ticketcar'}, {'Key': 'env', 'Value': 'prd'}])
        print(f'papel criado: {ROLE}')
    except iam.exceptions.EntityAlreadyExistsException:
        iam.update_assume_role_policy(RoleName=ROLE, PolicyDocument=json.dumps(trust))
        print(f'papel já existe (confiança atualizada): {ROLE}')
    bucket = state['bucket']
    policy = {'Version': '2012-10-17', 'Statement': [
        {'Sid': 'Listar', 'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': f'arn:aws:s3:::{bucket}'},
        {'Sid': 'Publicar', 'Effect': 'Allow', 'Action': ['s3:PutObject', 's3:DeleteObject'], 'Resource': f'arn:aws:s3:::{bucket}/*'},
        {'Sid': 'LimparCache', 'Effect': 'Allow', 'Action': 'cloudfront:CreateInvalidation',
         'Resource': f'arn:aws:cloudfront::{acct}:distribution/{state["distributionId"]}'},
    ]}
    iam.put_role_policy(RoleName=ROLE, PolicyName='site-publish', PolicyDocument=json.dumps(policy))
    print(f'permissões: {bucket} + invalidação da {state["distributionId"]}')


if __name__ == '__main__':
    main()
