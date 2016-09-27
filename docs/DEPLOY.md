# Working with Elastic Beanstalk

## Getting set up

Before you get started with Elastic Beanstalk, you'll have to install the `eb`
command line client, and configure your credentials. The CLI tool is installed
with:

```bash
pip install awsebcli awscli
```

*(Note that the AWS CLI is a different tool and the EB CLI, and both are
installed above)*

You can find credentials for working with the CLI in the IAM settings of the
AWS console. If you are using the CLI from your own work machine, look up your
username at https://console.aws.amazon.com/iam/home#users; if you are using the
CLI from a different machine, consider creating a new user. Any given set of
credentials should ideally only be used in one place so that they can be easily
and quickly deactivated if necessary with minimal impact.

If you don't have an IAM key pair, create one. Once you have your AWS key and
secret, you can configure your CLI credentials with:

```bash
aws configure --profile phila
```

This will set up your credentials in a profile named `phila`. This is the
profile that the AIS repository is configured to look for by default, and is
named `phila` so that it does not interfere with any other credentials you may
have installed on your machine.

Now you're ready to deploy.

# Deploying to AWS

There are two production-level environments for the AIS API: *ais-api-market*
and *ais-api-broad*. Generally, you shouldn't deploy directly to a production
environment. Deployments are managed by the [Travis](https://travis-ci.org)
continuous integration service. The master branch is automatically deployed
when it changes on GitHub.

## Deploying the database to RDS

The *scripts/update_db.sh* script can be used to run the engine update process.
This process entails:

1. Uploading the new database to the non-live production environment (*broad* or
   *market*),
2. Marking the non-live production environment as being ready to swap with the
   live one,
3. Running the API application tests against the database, and finally
4. Swapping the live environment, if the tests pass.

The last two steps are done on Travis CI. If the tests fail, the non-live
environment will remain in a ready-to-swap state until the tests pass again, at
which point Travis will make the swap.

**NOTE: the environments are marked as *Production*, *Staging*, or *Swap* using
  the environment variable `EB_BLUEGREEN_STATUS`. If the machines ever get out
  of sync, you can set this variable on the environments manually using `eb
  config set` (see below).**

## Deploying a development application

You can also create your own development environment. There are a couple of
saved configurations that you can choose to work from. These configurations are
saved on AWS and can be retrieved by running:

```bash
eb config list
```

To create a new environment for demoing a development branch, you can run, for
example:

```bash
eb create mynewdevenv --cfg ais-api-dev-sc
```

In the example above, `mynewdevenv` is the name of the new environment that I
am creating, and `ais-api-dev-sc` is the name of the saved configuration that I
am basing the environment on.

Once you have your test environment, you may want to specify what database it
reads from. You can do that by setting the `SQLALCHEMY_DATABASE_URI` environment
variable:

```bash
eb setenv -e mynewtestenv "SQLALCHEMY_DATABASE_URI=postgresql://dbuser:dbpass@ais-engine-db-dev.subdomain.us-east-1.rds.amazonaws.com:5432/ais_engine"
```

Now if you run `eb printenv mynewtestenv` you should see the variable set.

Finally, do deploy a particular branch to that development environment, check
out that branch and run the following:

```bash
eb deploy mynewtestenv
```
